"""
Swift Package Index scraper — iOS Swift Package Manager libraries.

SPI mirrors most Swift packages and provides a stable JSON API.
API: https://swiftpackageindex.com/api/packages/{owner}/{repo}/releases
"""
from __future__ import annotations
from datetime import datetime, timezone

import httpx

from ..exceptions import PackageNotFoundError, ParseError
from ..models.schemas import ScrapedVersion
from ..strategies.base import ScraperStrategy


class SwiftPackageIndexScraper(ScraperStrategy):
    """
    `package` format: 'owner/repo'   e.g. 'firebase/firebase-ios-sdk'
    """
    BASE_URL = "https://swiftpackageindex.com/api/packages"

    @property
    def registry_key(self) -> str:
        return "spm"

    async def fetch(self, package: str, **kwargs: object) -> ScrapedVersion:
        if "/" not in package:
            raise ParseError(
                f"SPI package must be 'owner/repo', got: '{package}'"
            )

        owner, repo = package.split("/", 1)
        url = f"{self.BASE_URL}/{owner}/{repo}/releases"

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers={"Accept": "application/json"})

        if response.status_code == 404:
            raise PackageNotFoundError(f"Package '{package}' not found on Swift Package Index")
        response.raise_for_status()

        data = response.json()
        releases: list[dict] = data if isinstance(data, list) else data.get("releases", [])

        if not releases:
            raise PackageNotFoundError(f"No releases found for '{package}' on Swift Package Index")

        # Releases are newest-first
        latest = releases[0]
        version = latest.get("version")
        if not version:
            raise ParseError(f"SPI release missing 'version' field for '{package}'")

        release_date: str | None = None
        published_at = latest.get("publishedAt")
        if published_at:
            try:
                release_date = published_at[:10]
            except Exception:
                pass

        return ScrapedVersion(
            package=package,
            registry=self.registry_key,
            latest_version=version,
            release_date=release_date,
            source_url=f"https://swiftpackageindex.com/{owner}/{repo}",
            scraped_at=datetime.now(timezone.utc),
        )
