"""Central application configuration.

All settings are loaded from environment variables or a `.env` file located
in the `backend/` working directory. Secrets must never be hard-coded.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Application
    APP_NAME: str = "CronPanel"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BCRYPT_ROUNDS: int = 12

    # Login brute-force protection
    LOGIN_RATE_LIMIT: int = 5
    LOGIN_RATE_WINDOW_SECONDS: int = 300

    # Execution engine (Phase 4)
    EXECUTION_TIMEOUT_SECONDS: int = 10
    EXECUTION_OUTPUT_MAX_CHARS: int = 65536
    EXECUTION_SCRIPTS_DIR: str = ""

    # Password policy
    PASSWORD_MIN_LENGTH: int = 10

    # Database
    DATABASE_URL: str = f"sqlite:///{(BASE_DIR / 'cronpanel.db').as_posix()}"

    # CORS (comma separated list of allowed origins)
    CORS_ORIGINS: str = "http://localhost:8000"

    @field_validator("SECRET_KEY")
    @classmethod
    def require_strong_secret(cls, value: str) -> str:
        if not value:
            raise ValueError(
                "SECRET_KEY is required. Copy .env.example to .env and generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if len(value) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters long."
            )
        return value

    @field_validator("ALGORITHM")
    @classmethod
    def validate_algorithm(cls, value: str) -> str:
        allowed = {"HS256", "HS384", "HS512"}
        if value not in allowed:
            raise ValueError(f"ALGORITHM must be one of {sorted(allowed)}.")
        return value

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def validate_token_expiration(cls, value: int) -> int:
        if not 1 <= value <= 1440:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and 1440.")
        return value

    @field_validator("BCRYPT_ROUNDS")
    @classmethod
    def validate_bcrypt_rounds(cls, value: int) -> int:
        if not 4 <= value <= 31:
            raise ValueError("BCRYPT_ROUNDS must be between 4 and 31.")
        return value

    @field_validator("LOGIN_RATE_LIMIT")
    @classmethod
    def validate_login_rate_limit(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("LOGIN_RATE_LIMIT must be between 1 and 100.")
        return value

    @field_validator("LOGIN_RATE_WINDOW_SECONDS")
    @classmethod
    def validate_login_rate_window(cls, value: int) -> int:
        if not 1 <= value <= 86400:
            raise ValueError("LOGIN_RATE_WINDOW_SECONDS must be between 1 and 86400.")
        return value

    @field_validator("EXECUTION_TIMEOUT_SECONDS")
    @classmethod
    def validate_execution_timeout(cls, value: int) -> int:
        if not 1 <= value <= 300:
            raise ValueError("EXECUTION_TIMEOUT_SECONDS must be between 1 and 300.")
        return value

    @field_validator("EXECUTION_OUTPUT_MAX_CHARS")
    @classmethod
    def validate_execution_output_max_chars(cls, value: int) -> int:
        if not 1024 <= value <= 1_000_000:
            raise ValueError("EXECUTION_OUTPUT_MAX_CHARS must be between 1024 and 1000000.")
        return value

    @property
    def execution_scripts_dir(self) -> Path:
        """Root directory that hosts allowed script files.

        Everything the executor launches must live under this directory; any
        path escaping it is rejected by the policy layer before execution.
        """
        value = self.EXECUTION_SCRIPTS_DIR.strip()
        root = Path(value) if value else BASE_DIR / "scripts_allowlist"
        return root.expanduser().resolve()

    @field_validator("PASSWORD_MIN_LENGTH")
    @classmethod
    def validate_password_min_length(cls, value: int) -> int:
        if not 8 <= value <= 128:
            raise ValueError("PASSWORD_MIN_LENGTH must be between 8 and 128.")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
