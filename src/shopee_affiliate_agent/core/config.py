from decimal import Decimal
from functools import lru_cache
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    INTERNAL_API_TOKEN: SecretStr
    POSTGRES_DB: str = "shopee_affiliate"
    POSTGRES_APP_USER: str = "shopee_app"
    POSTGRES_APP_PASSWORD: SecretStr
    POSTGRES_MIGRATION_USER: str = "shopee_migrator"
    POSTGRES_MIGRATION_PASSWORD: SecretStr
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    REDIS_PASSWORD: SecretStr
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    BUSINESS_TIMEZONE: str = "America/Sao_Paulo"
    AUTO_PUBLICATION_ENABLED: bool = False
    HUMAN_APPROVAL_REQUIRED: bool = True
    PRICE_VALIDATION_MAX_AGE_MINUTES: int = Field(default=60, gt=0)
    SCORE_WEIGHT_CONVERSION_POTENTIAL: Decimal = Decimal("30")
    SCORE_WEIGHT_NET_COMMISSION: Decimal = Decimal("20")
    SCORE_WEIGHT_PRODUCT_QUALITY: Decimal = Decimal("15")
    SCORE_WEIGHT_PRICE_STOCK_STABILITY: Decimal = Decimal("10")
    SCORE_WEIGHT_NICHE_FIT: Decimal = Decimal("10")
    SCORE_WEIGHT_VIDEO_DEMONSTRATION_POTENTIAL: Decimal = Decimal("10")
    SCORE_WEIGHT_CANCELLATION_QUALITY: Decimal = Decimal("5")

    @field_validator("AUTO_PUBLICATION_ENABLED")
    @classmethod
    def automatic_publication_must_remain_disabled(cls, value: bool) -> bool:
        if value:
            raise ValueError("automatic publication must remain disabled")
        return value

    @field_validator("HUMAN_APPROVAL_REQUIRED")
    @classmethod
    def human_approval_must_remain_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("human approval must remain required")
        return value

    @property
    def database_url(self) -> str:
        password = quote(self.POSTGRES_APP_PASSWORD.get_secret_value(), safe="")
        return (
            f"postgresql+psycopg://{self.POSTGRES_APP_USER}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def migration_database_url(self) -> str:
        password = quote(self.POSTGRES_MIGRATION_PASSWORD.get_secret_value(), safe="")
        return (
            f"postgresql+psycopg://{self.POSTGRES_MIGRATION_USER}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        password = quote(self.REDIS_PASSWORD.get_secret_value(), safe="")
        return f"redis://:{password}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
