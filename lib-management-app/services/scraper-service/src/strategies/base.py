"""
Scraper Service — abstract base + ScraperFactory.

Architecture (Section 4.2):
  - ScraperStrategy: one implementation per registry
  - ScraperFactory: dict-based plugin registry; add new ecosystem = one line
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from ..exceptions import RegistryNotSupportedError
from ..models.schemas import ScrapedVersion


# ── Abstract base ──────────────────────────────────────────────────────────────

class ScraperStrategy(ABC):
    """
    All concrete scrapers implement exactly two things:
      1. `registry_key` — string key matching scraper_registry_config.registry_key
      2. `fetch(package, **kwargs)` — returns ScrapedVersion or raises
    """

    @property
    @abstractmethod
    def registry_key(self) -> str: ...

    @abstractmethod
    async def fetch(self, package: str, **kwargs: object) -> ScrapedVersion:
        """
        Fetch the latest version for `package` from this registry.

        Extra kwargs (strategy-specific):
          - custom_url: str  (CustomHTTPScraper)
          - github_token: str  (GitHubReleasesScraper)

        Raises:
          PackageNotFoundError  — package not found in registry
          ParseError            — unexpected response shape
          httpx.HTTPError       — network / HTTP failure
        """


# ── Factory ─────────────────────────────────────────────────────────────────────

class ScraperFactory:
    """
    Plugin registry.  Strategies are registered at startup in main.py.
    Adding a new ecosystem:
        1. Create strategies/<name>.py  implementing ScraperStrategy
        2. ScraperFactory.register('<key>', MyNewScraper())   ← one line in main.py
        3. Insert row in scraper_registry_config DB table
    """
    _registry: dict[str, ScraperStrategy] = {}

    @classmethod
    def register(cls, strategy: ScraperStrategy) -> None:
        cls._registry[strategy.registry_key] = strategy

    @classmethod
    def get(cls, registry_key: str) -> ScraperStrategy:
        if registry_key not in cls._registry:
            raise RegistryNotSupportedError(
                f"No scraper registered for registry '{registry_key}'. "
                f"Available: {list(cls._registry.keys())}"
            )
        return cls._registry[registry_key]

    @classmethod
    def available_keys(cls) -> list[str]:
        return list(cls._registry.keys())
