import pytest
from pydantic import ValidationError

from shopee_affiliate_agent.core.config import Settings


def minimal_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "INTERNAL_API_TOKEN": "test-token-long-enough",
        "POSTGRES_APP_PASSWORD": "test-app-password",
        "POSTGRES_MIGRATION_PASSWORD": "test-migration-password",
        "REDIS_PASSWORD": "test-redis-password",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_publication_defaults_are_safe() -> None:
    settings = minimal_settings()
    assert settings.AUTO_PUBLICATION_ENABLED is False
    assert settings.HUMAN_APPROVAL_REQUIRED is True


@pytest.mark.parametrize(
    "override", [{"AUTO_PUBLICATION_ENABLED": True}, {"HUMAN_APPROVAL_REQUIRED": False}]
)
def test_unsafe_publication_configuration_is_rejected(override: dict[str, bool]) -> None:
    with pytest.raises(ValidationError):
        minimal_settings(**override)
