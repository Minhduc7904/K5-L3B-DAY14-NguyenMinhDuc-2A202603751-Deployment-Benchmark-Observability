"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Không có secret nào được ghi trong code. Giá trị mẫu nằm ở .env.example,
giá trị thật được đặt qua môi trường (docker compose, Railway, Render...).
"""
import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10))
    daily_budget_usd: float = field(default_factory=lambda: _env_float("DAILY_BUDGET_USD", 1.0))

    def validate(self) -> "Settings":
        """Fail fast: production mà thiếu API key thì không cho khởi động."""
        if self.environment == "production" and not self.agent_api_key:
            raise ValueError("AGENT_API_KEY must be set when ENVIRONMENT=production")
        return self


settings = Settings().validate()
