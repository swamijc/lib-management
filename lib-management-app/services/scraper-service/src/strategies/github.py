"""
GitHub Releases scraper — vendored / binary SDKs that only publish via GitHub.

API: https://api.github.com/repos/{owner}/{repo}/releases/latest
`package` format: 'owner/repo'   e.g. 'airbnb/lottie-ios'
"""
from __future__ import annotations
from datetime import datetime, timezone

import httpx

from ..exceptions import PackageNotFoundError, ParseError
from ..models.schemas import ScrapedVersion
from ..strategies.base import ScraperStrategy


class GitHubReleasesScraper(ScraperStrategy):
    BASE_URL = "https://api.github.com/repos"

    @property
    def registry_key(self) -> str:
        return "github"

    async def fetch(self, package: str, **kwargs: object) -> ScrapedVersion:
        """
        kwargs:
          github_token: str  — optional Bearer token to avoid rate-limiting
        """
        if "/" not in package:
            raise ParseError(
                f"GitHub package must be 'owner/repo', got: '{package}'"
            )

        owner, repo = package.split("/", 1)
        url = f"{self.BASE_URL}/{owner}/{repo}/releases/latest"

        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = str(kwargs.get("github_token", ""))
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            response = await client.get(url, headers=headers)

        if response.status_code == 404:
            raise PackageNotFoundError(
                f"Repository '{package}' not found on GitHub or has no releases"
            )
        response.raise_for_status()

        data = response.json()

        # `tag_name` may be 'v1.2.3' — strip leading 'v' for consistency
        tag = data.get("tag_name", "")
        version = tag.lstrip("v") if tag else None
        if not version:
            raise ParseError(f"GitHub release missing 'tag_name' for '{package}'")

        release_date: str | None = None
        published_at = data.get("published_at")
        if published_at:
            try:
                release_date = published_at[:10]
            except Exception:
                pass

        # Release body truncated to 2000 chars to avoid DB bloat
        body: str | None = data.get("body")
        release_notes = body[:2000] if body else None

        return ScrapedVersion(
            package=package,
            registry=self.registry_key,
            latest_version=version,
            release_notes=release_notes,
            release_date=release_date,
            source_url=data.get("html_url"),
            scraped_at=datetime.now(timezone.utc),
        )
