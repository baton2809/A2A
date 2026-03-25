import random

from ..providers.schema import LLMProvider
from .base import BaseRouter


class WeightedRouter(BaseRouter):
    """Выбирает провайдера с вероятностью пропорциональной весу."""

    def pick(self, providers: list[LLMProvider]) -> LLMProvider | None:
        if not providers:
            return None
        weights = [p.weight for p in providers]
        return random.choices(providers, weights=weights, k=1)[0]
