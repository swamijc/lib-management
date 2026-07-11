"""
CocoaPods Trunk scraper — iOS pods.

API: https://trunk.cocoapods.org/api/v1/pods/{name}
"""
from __future__ import annotations
from datetime import datetime, timezone

import httpx

from ..exceptions import PackageNotFoundError, ParseError
from ..models.schemas import ScrapedVersion
from ..strategies.base import ScraperStrategy


class CocoaPodsScraper(ScraperStrategy):
    BASE_URL = "https://trunk.cocoapods.org/api/v1/pods"

    @property
    def registry_key(self) -> str:
        return "cocoapods"

    async def fetch(self, package: str, **kwargs: object) -> ScrapedVersion:
        url = f"{self.BASE_URL}/{package}"

        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            response = await client.get(url, headers={"User-Agent": "LibManagePlatform/1.0"})

        if response.status_code == 404:
            raise PackageNotFoundError(f"Pod '{package}' not found on CocoaPods Trunk")
        response.raise_for_status()

        data = response.json()
        versions: list[dict] = data.get("versions", [])
        if not versions:
            raise ParseError(f"CocoaPods response has no versions for '{package}'")

        # Versions are returned in ascending order; last is latest
        latest = versions[-1]
        version = latest.get("name")
        if not version:
            raise ParseError(f"CocoaPods version entry missing 'name' field for '{package}'")

        release_date: str | None = None
        created_at = latest.get("created_at")
        if created_at:
            try:
                release_date = created_at[:10]  # ISO-8601 prefix
            except Exception:
                pass

        return ScrapedVersion(
            package=package,
            registry=self.registry_key,
            latest_version=version,
            release_date=release_date,
            source_url=f"https://cocoapods.org/pods/{package}",
            scraped_at=datetime.now(timezone.utc),
        )
