"""
Recommendation Service — abstract generator base.

Every generator (rule-based or LLM) implements `generate()`.
The factory picks the right one at runtime.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from ..models.schemas import RecommendationRequest, RecommendationResult


class RecommendationGenerator(ABC):

    @abstractmethod
    async def generate(self, req: RecommendationRequest) -> RecommendationResult: ...

    @property
    @abstractmethod
    def generator_type(self) -> str: ...
