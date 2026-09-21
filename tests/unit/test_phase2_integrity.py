from pytest import MonkeyPatch

from shopee_affiliate_agent.api.schemas import ProductCreate


def test_manual_product_schema_does_not_accept_source() -> None:
    schema = ProductCreate.model_json_schema()
    assert "source" not in schema["properties"]


def test_import_delivery_has_bounded_publish_retry_and_single_worker(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-token-not-secret")
    monkeypatch.setenv("POSTGRES_APP_PASSWORD", "test-password-not-secret")
    monkeypatch.setenv("POSTGRES_MIGRATION_PASSWORD", "test-password-not-secret")
    monkeypatch.setenv("REDIS_PASSWORD", "test-password-not-secret")
    from shopee_affiliate_agent.worker import celery_app

    assert celery_app.conf.task_publish_retry is True
    assert celery_app.conf.worker_concurrency == 1
    policy = celery_app.conf.task_publish_retry_policy
    assert policy["max_retries"] == 4
    assert "dispatch-import-outbox-every-10-seconds" in celery_app.conf.beat_schedule
