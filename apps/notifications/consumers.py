import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

class GlobalEventConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 1. Accept connection first to complete handshake
        await self.accept()

        try:
            # 2. Parse query params safely
            query_string = parse_qs(self.scope.get('query_string', b'').decode())
            user_hash = query_string.get('user_hash', [None])[0]

            # 3. Add to global Redis group
            if self.channel_layer is not None:
                await self.channel_layer.group_add('logs_table', self.channel_name)

                # 4. Add to user-specific group if user_hash present
                if user_hash:
                    self.user_group = f"user_events_{user_hash}"
                    await self.channel_layer.group_add(self.user_group, self.channel_name)

        except Exception as e:
            logger.error(f"❌ Exception in GlobalEventConsumer.connect: {e}", exc_info=True)
            await self.close(code=4000)

    async def disconnect(self, close_code):
        try:
            if self.channel_layer is not None:
                await self.channel_layer.group_discard('logs_table', self.channel_name)
                if hasattr(self, 'user_group'):
                    await self.channel_layer.group_discard(self.user_group, self.channel_name)
        except Exception as e:
            logger.error(f"❌ Error during group_discard in disconnect: {e}")

    # Optional: Receive messages sent from JS frontend
    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            try:
                data = json.loads(text_data)
                # Handle client actions if needed
            except json.JSONDecodeError:
                pass

    # Handler for messages sent from Go worker via Redis
    async def global_event(self, event):
        await self.send(text_data=json.dumps(event['data']))