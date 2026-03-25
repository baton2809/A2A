import itertools

from ..providers.schema import LLMProvider
from .base import BaseRouter


class RoundRobinRouter(BaseRouter):
    """Циклически перебирает провайдеров."""

    def __init__(self) -> None:
        self._counter = itertools.count()

    def pick(self, providers: list[LLMProvider]) -> LLMProvider | None:
        if not providers:
            return None
        idx = next(self._counter) % len(providers)
        return providers[idx]
