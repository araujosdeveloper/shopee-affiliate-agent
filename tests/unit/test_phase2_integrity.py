from shopee_affiliate_agent.api.schemas import ProductCreate
from shopee_affiliate_agent.worker import celery_app


def test_manual_product_schema_does_not_accept_source() -> None:
    schema = ProductCreate.model_json_schema()
    assert "source" not in schema["properties"]


def test_import_delivery_has_bounded_publish_retry_and_single_worker() -> None:
    assert celery_app.conf.task_publish_retry is True
    assert celery_app.conf.worker_concurrency == 1
    policy = celery_app.conf.task_publish_retry_policy
    assert policy["max_retries"] == 4
    assert "dispatch-import-outbox-every-10-seconds" in celery_app.conf.beat_schedule
