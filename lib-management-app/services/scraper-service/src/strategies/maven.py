"""
Maven Central scraper — Android / Java libraries.

Uses repo1.maven.org/maven2/{group}/{artifact}/maven-metadata.xml
(direct metadata, works without SSL verification issues).
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from ..exceptions import PackageNotFoundError, ParseError
from ..models.schemas import ScrapedVersion
from ..strategies.base import ScraperStrategy

_HEADERS = {"User-Agent": "LibManagePlatform/1.0 (internal)"}
_GOOGLE_MAVEN_GROUPS = (
    "androidx.", "com.google.android.", "com.google.firebase.",
    "com.google.gms.", "com.android.",
)


class MavenCentralScraper(ScraperStrategy):

    @property
    def registry_key(self) -> str:
        return "maven"

    async def fetch(self, package: str, **kwargs: object) -> ScrapedVersion:
        """
        `package` must be Maven coordinates: 'groupId:artifactId'
        e.g. 'com.google.firebase:firebase-bom'
        """
        if ":" not in package:
            raise ParseError(f"Maven package must be 'groupId:artifactId', got: '{package}'")

        group, artifact = package.split(":", 1)
        path = group.replace(".", "/") + "/" + artifact

        # Choose the right base depending on group prefix
        is_google = any(group.startswith(p) for p in _GOOGLE_MAVEN_GROUPS)
        if is_google:
            metadata_url = f"https://dl.google.com/dl/android/maven2/{path}/maven-metadata.xml"
        else:
            metadata_url = f"https://repo1.maven.org/maven2/{path}/maven-metadata.xml"

        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            resp = await client.get(metadata_url, headers=_HEADERS)
            if resp.status_code == 404 and is_google:
                # Fallback: try Maven Central
                metadata_url = f"https://repo1.maven.org/maven2/{path}/maven-metadata.xml"
                resp = await client.get(metadata_url, headers=_HEADERS)
            if resp.status_code == 404:
                raise PackageNotFoundError(f"Package '{package}' not found on Maven")
            resp.raise_for_status()

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            raise ParseError(f"Invalid XML from Maven for '{package}': {e}") from e

        versioning = root.find("versioning")
        if versioning is None:
            raise ParseError(f"No <versioning> element in metadata for '{package}'")

        version = (
            versioning.findtext("release")
            or versioning.findtext("latest")
        )
        if not version:
            # Last entry in <versions> list
            versions_el = versioning.find("versions")
            if versions_el is not None:
                all_v = [v.text for v in versions_el.findall("version") if v.text]
                version = all_v[-1] if all_v else None

        if not version:
            raise ParseError(f"No version found in Maven metadata for '{package}'")

        # Release date from lastUpdated (format: YYYYMMDDHHmmss)
        last_updated = versioning.findtext("lastUpdated")
        release_date: str | None = None
        if last_updated and len(last_updated) >= 8:
            try:
                release_date = f"{last_updated[:4]}-{last_updated[4:6]}-{last_updated[6:8]}"
            except Exception:
                pass

        return ScrapedVersion(
            package=package,
            registry=self.registry_key,
            latest_version=version,
            release_date=release_date,
            source_url=f"https://mvnrepository.com/artifact/{group}/{artifact}/{version}",
            scraped_at=datetime.now(timezone.utc),
        )
