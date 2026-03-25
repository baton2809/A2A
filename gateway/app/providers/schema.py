from pydantic import BaseModel, Field


class LLMProvider(BaseModel):
    """Данные о провайдере LLM.

    Включает конфигурацию (Level 1), ценовые/лимитные поля (Level 2)
    и runtime-состояние circuit breaker / EMA.
    """

    name: str
    url: str
    models: list[str] = Field(default_factory=lambda: ["*"])  # "*" — поддерживает любую модель
    weight: int = Field(default=1, ge=1)
    timeout_s: float = Field(default=30.0, ge=1.0)  # таймаут запроса

    # Level 2: ценообразование и лимиты
    price_per_token: float = Field(default=0.0, ge=0.0)   # USD за токен (0 = не задано)
    request_limit: int = Field(default=0, ge=0)            # RPM лимит (0 = безлимитный)
    priority: int = Field(default=0, ge=0)                 # чем выше — тем предпочтительнее

    # Runtime-состояние (не редактируется пользователем напрямую)
    healthy: bool = True
    latency_ema: float = 0.0       # EMA задержки, секунды
    error_streak: int = 0          # подряд идущих ошибок
    cooldown_until: float = 0.0    # unix timestamp конца паузы


class ProviderIn(BaseModel):
    """Тело запроса при регистрации провайдера."""

    name: str
    url: str
    models: list[str] = ["*"]
    weight: int = Field(default=1, ge=1)
    timeout_s: float = Field(default=30.0, ge=1.0)
    price_per_token: float = Field(default=0.0, ge=0.0)
    request_limit: int = Field(default=0, ge=0)
    priority: int = Field(default=0, ge=0)
