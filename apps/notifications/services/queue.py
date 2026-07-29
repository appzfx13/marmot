import logging
from notifications.models import RiverJob

logger = logging.getLogger(__name__)

def enqueue_river_job(kind: str, args: dict, queue: str = "default", max_attempts: int = 3) -> RiverJob:
    """
    Common helper to enqueue any job directly into River's PostgreSQL table via Django ORM.
    """
    try:
        job = RiverJob.objects.create(
            kind=kind,
            args=args,
            queue=queue,
            state="available",
            max_attempts=max_attempts,
        )
        logger.info(f"Enqueued River job [{kind}] with ID {job.id}")
        return job
    except Exception as e:
        logger.error(f"Failed to enqueue River job [{kind}]: {e}")
        raise e


def enqueue_send_otp_job(phone_number: str, otp_code: str):
    """
    Convenience wrapper specifically for dispatching OTP jobs.
    """
    return enqueue_river_job(
        kind="send_otp",
        args={
            "phone_number": phone_number,
            "otp_code": otp_code,
        },
    )