from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "my-web-backend"
    DEBUG: bool = False

    DATABASE_URL: str = Field(min_length=1)
    JWT_SECRET_KEY: str = Field(min_length=1)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    CORS_ORIGINS: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]
    TRUSTED_HOSTS: list[str] = ["127.0.0.1", "localhost", "testserver"]
    LOG_LEVEL: str = "INFO"
    RATE_LIMIT_GENERAL: int = 120
    RATE_LIMIT_AUTH: int = 10
    RATE_LIMIT_CHAT: int = 30
    RATE_LIMIT_FEEDBACK: int = 10
    # Behind a reverse proxy (nginx) every socket peer is the proxy IP. Only
    # trust X-Forwarded-For / X-Real-IP when explicitly opted in (production).
    # Default off so a direct client cannot spoof the header to bypass limits.
    TRUST_PROXY_HEADERS: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 1800

    @field_validator("TRUSTED_HOSTS", "CORS_ORIGINS", mode="before")
    @classmethod
    def parse_list(cls, value):
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # LLM (OpenAI-compatible provider)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""
    LLM_FAST_MODEL: str = ""
    LLM_STANDARD_MODEL: str = ""
    LLM_REASONING_MODEL: str = ""
    LLM_PROVIDER_LABEL: str = "openai_compatible"
    LLM_TIMEOUT: float = 30.0
    AGENT_MAX_STEPS: int = 6

    # Embeddings (OpenAI-compatible provider)
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_MODEL: str = ""
    EMBEDDING_TIMEOUT: float = 30.0

    RAG_UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads")
    RAG_MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 150
    RAG_MAX_CONTEXT_CHARS: int = 12000
    WORKFLOW_MAX_STEP_ATTEMPTS: int = 3
    CREDIT_GRANT_ON_REGISTER: int = 1000
    CREDIT_INPUT_RATE: float = 1.0
    CREDIT_OUTPUT_RATE: float = 2.0

    # Classroom Beta: registration requires a valid invite code by default.
    # This closes the open-registration + BETA_REGISTER_CREDITS farming loop
    # (security P0). Dev environments may opt out via INVITE_REQUIRED=false.
    INVITE_REQUIRED: bool = True
    BETA_REGISTER_CREDITS: int = 2000
    # Referral rewards are DISABLED (0) for Classroom Beta: self-referral
    # farming cannot be reliably detected without IP/device identity tracking.
    REFERRAL_REWARD_CREDITS: int = 0
    REFERRAL_NEW_USER_CREDITS: int = 0
    MAX_CHAT_IMAGE_SIZE: int = 10 * 1024 * 1024
    MAX_CHAT_IMAGES_PER_MESSAGE: int = 4
    VISION_BASE_CREDIT_COST: int = 0
    # Minimum credits charged per text chat turn even when the provider does not
    # report streaming usage (OpenAI-compatible fallback without include_usage).
    # 0 -> floor of 1 credit. Mirrors VISION_BASE_CREDIT_COST for text.
    CHAT_BASE_CREDIT_COST: int = 0
    # Worst-case completion token budget used for the pre-generation balance
    # check (P1-2 TOCTOU): fail fast before burning provider tokens.
    CHAT_COMPLETION_BUDGET_TOKENS: int = 1024
    # Explicitly assign the vision variant to ONE cost tier; never cross tiers.
    VISION_MODEL: str = ""
    VISION_MODEL_TIER: str = "standard"
    # Optional OpenAI-compatible vision endpoint (e.g. siliconflow); when both
    # are set, vision requests use these instead of the text LLM endpoint.
    VISION_API_KEY: str = ""
    VISION_BASE_URL: str = ""
    MAX_CHAT_IMAGE_BASE64_SIZE: int = 14 * 1024 * 1024
    MAX_CHAT_IMAGES_PER_CONVERSATION: int = 4
    TAOTOKEN_API_KEY: str = ""
    TAOTOKEN_BASE_URL: str = ""
    TAOTOKEN_VISION_MODEL: str = ""
    # Vision models (e.g. Taotoken kimi-k3) can take well over a minute for the
    # first token; keep them on a longer budget than text LLM_TIMEOUT.
    VISION_TIMEOUT: float = 180.0
    ANALYTICS_ACTIVE_DAYS: int = 7
    PAYMENT_QR_IMAGE_URL: str = ""

    # Custom recharge pricing. Server-owned: the client never computes credits.
    # Money is Decimal; never use float for CNY amounts.
    CUSTOM_RECHARGE_ENABLED: bool = True
    CREDIT_PER_CNY: Decimal = Decimal("300")
    CUSTOM_RECHARGE_MIN_CNY: Decimal = Decimal("1")
    CUSTOM_RECHARGE_MAX_CNY: Decimal = Decimal("500")
    CUSTOM_RECHARGE_STEP_CNY: Decimal = Decimal("1")
    RECHARGE_PRICING_VERSION: str = "v1"

    # Asynchronous document processing. Redis is deliberately optional for the
    # API process: it is opened only when a task is dispatched.
    REDIS_URL: str = ""
    DOCUMENT_TASK_QUEUE: str = "document-processing"
    DOCUMENT_TASK_MAX_RETRIES: int = 5
    DOCUMENT_TASK_RETRY_BASE_SECONDS: float = 60.0
    DOCUMENT_TASK_RETRY_MAX_SECONDS: float = 3600.0
    DOCUMENT_TASK_LEASE_SECONDS: float = 300.0
    DOCUMENT_TASK_DISPATCH_INTERVAL_SECONDS: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# Server-owned Classroom Beta recharge catalog.
RECHARGE_PACKAGES = {
    "experience": {"credits": 1000, "amount_display": "10 CNY"},
}
