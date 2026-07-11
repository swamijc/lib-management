"""Abstract repository interface — decouples business logic from persistence."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TypeVar, Generic

T = TypeVar("T")
ID = TypeVar("ID")


class AbstractRepository(ABC, Generic[T, ID]):
    @abstractmethod
    async def get_by_id(self, id: ID) -> T | None: ...

    @abstractmethod
    async def get_all(self) -> list[T]: ...
