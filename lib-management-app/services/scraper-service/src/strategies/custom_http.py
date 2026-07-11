"""
Custom HTTP scraper — admin-configured URL per library.

Used for: ACI/IPWorks, Scandit, Gigya, and any SDK that doesn't appear
          in any standard registry.

The caller supplies `custom_url` in the request.  The scraper GETs that URL
and tries:
  1. JSON response  — hunts for common version field names.
  2. HTML response  — extracts all "Version X.Y.Z" headings (e.g. OPPWa docs).
"""
from __future__ import annotations
import re
from datetime import datetime, timezone

import httpx

from ..exceptions import PackageNotFoundError, ParseError
from ..models.schemas import ScrapedVersion
from ..strategies.base import ScraperStrategy

# Ordered list of JSON field names to try when hunting for a version string
_VERSION_FIELD_CANDIDATES = [
    "version", "latest_version", "latestVersion", "tag_name",
    "current_version", "release", "name",
]

# Matches headings like:  ### Version 7.12.1  or  ## Version 2.3.9149
_HTML_VERSION_RE = re.compile(
    r"(?:#{1,4}\s+Version\s+|Version\s+)([\d]+\.[\d]+(?:\.[\d]+)*)",
    re.IGNORECASE,
)


def _parse_versions_from_html(html: str) -> list[str]:
    """Return de-duplicated list of versions found in HTML, order preserved (newest first)."""
    seen: set[str] = set()
    result: list[str] = []
    for m in _HTML_VERSION_RE.finditer(html):
        v = m.group(1).strip()
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


class CustomHTTPScraper(ScraperStrategy):
    """
    Performs a GET on `custom_url` (provided at scrape-time).
    Supports JSON (field-scan) and HTML (heading-based version extraction).
    """

    @property
    def registry_key(self) -> str:
        return "custom"

    async def fetch(self, package: str, **kwargs: object) -> ScrapedVersion:
        """
        kwargs:
          custom_url: str  — REQUIRED; the admin-configured endpoint URL
        """
        custom_url = str(kwargs.get("custom_url", "")).strip()
        if not custom_url:
            raise ParseError(
                f"Custom registry requires 'custom_url' for package '{package}'"
            )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                custom_url,
                follow_redirects=True,
                headers={"User-Agent": "LibManagement-Scraper/1.0"},
            )

        if response.status_code == 404:
            raise PackageNotFoundError(
                f"Custom URL returned 404 for '{package}': {custom_url}"
            )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()

        # ── Path 1: JSON response ─────────────────────────────────────────────
        if "json" in content_type or response.text.lstrip().startswith(("{", "[")):
            try:
                data = response.json()
            except Exception:
                raise ParseError(
                    f"Custom URL response looks like JSON but failed to parse for '{package}': {custom_url}"
                )
            version: str | None = None
            for field in _VERSION_FIELD_CANDIDATES:
                candidate = data.get(field)
                if candidate and isinstance(candidate, str):
                    version = candidate.lstrip("v")
                    break
            if not version:
                raise ParseError(
                    f"Custom URL JSON response contains none of the expected version fields "
                    f"{_VERSION_FIELD_CANDIDATES} for '{package}'"
                )
            return ScrapedVersion(
                package=package,
                registry=self.registry_key,
                latest_version=version,
                source_url=custom_url,
                scraped_at=datetime.now(timezone.utc),
            )

        # ── Path 2: HTML response — extract version headings ─────────────────
        versions = _parse_versions_from_html(response.text)
        if not versions:
            raise ParseError(
                f"Could not parse any version headings from HTML at '{custom_url}' for '{package}'"
            )

        return ScrapedVersion(
            package=package,
            registry=self.registry_key,
            latest_version=versions[0],          # first heading = newest
            version_history=versions,             # full list for DB population
            source_url=custom_url,
            scraped_at=datetime.now(timezone.utc),
        )

