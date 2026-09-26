import json
import logging
import time
import redis
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.postback.services import PostbackService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs a lightweight worker to process webhooks from the Redis Stream'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting lightweight Webhook Worker..."))
        
        try:
            r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            r.ping()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to connect to Redis: {e}"))
            return

        stream_name = 'marmot:webhooks:stream'
        group_name = 'webhook_workers'
        consumer_name = 'worker-1'

        # Create consumer group if it doesn't exist
        try:
            r.xgroup_create(stream_name, group_name, id='0', mkstream=True)
            self.stdout.write(self.style.SUCCESS(f"Created consumer group '{group_name}'"))
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP Consumer Group name already exists" not in str(e):
                self.stdout.write(self.style.ERROR(f"Error creating group: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Listening to stream '{stream_name}'..."))

        while True:
            try:
                # Block for 2 seconds waiting for new messages
                messages = r.xreadgroup(group_name, consumer_name, {stream_name: '>'}, count=10, block=2000)
                
                if not messages:
                    continue

                for stream, message_list in messages:
                    for message_id, data in message_list:
                        try:
                            payload = json.loads(data.get('payload', '{}'))
                            user_id = data.get('user_id')
                            if user_id:
                                user_id = int(user_id)
                            broker_hint = data.get('broker_hint', 'dhan')
                            ip_address = data.get('ip_address', '')
                            execution_mode = data.get('execution_mode', 'LIVE')

                            # If it's a mock, we modify the payload just like the view used to
                            if execution_mode == 'MOCK':
                                payload['execution_mode'] = 'MOCK'

                            log = PostbackService.process_postback(
                                payload=payload,
                                user_id=user_id,
                                broker_hint=broker_hint,
                                ip_address=ip_address
                            )
                            
                            self.stdout.write(self.style.SUCCESS(f"Processed {broker_hint} webhook (ID: {log.id})"))
                            
                            # Acknowledge the message so it's removed from pending
                            r.xack(stream_name, group_name, message_id)
                            
                        except Exception as process_exc:
                            self.stdout.write(self.style.ERROR(f"Error processing message {message_id}: {process_exc}"))
                            # Route failed payload to DLQ stream and ACK to prevent infinite pending PEL memory accumulation
                            try:
                                r.xadd('marmot:webhooks:dlq', {
                                    'error': str(process_exc),
                                    'original_id': str(message_id),
                                    'payload': json.dumps(data)
                                }, maxlen=5000, approximate=True)
                                r.xack(stream_name, group_name, message_id)
                            except Exception:
                                pass
            except Exception as loop_exc:
                self.stdout.write(self.style.ERROR(f"Worker loop error: {loop_exc}"))
                time.sleep(2)
