from abc import ABC, abstractmethod

from ..providers.schema import LLMProvider


class BaseRouter(ABC):
    """Базовый интерфейс стратегии выбора провайдера."""

    @abstractmethod
    def pick(self, providers: list[LLMProvider]) -> LLMProvider | None:
        ...
