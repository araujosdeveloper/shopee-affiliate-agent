from celery import Celery

from shopee_affiliate_agent.core.config import get_settings

settings = get_settings()
celery_app = Celery("shopee_affiliate_agent", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
