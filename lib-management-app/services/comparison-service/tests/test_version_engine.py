"""
Unit tests for version_engine.compare_versions().

Covers: semver, non-semver, internal markers, unknown, bump classification.
"""
from __future__ import annotations
import pytest
from src.models.schemas import VersionStatus
from src.services.version_engine import compare_versions


def _compare(current: str, latest: str, **kwargs) -> object:
    return compare_versions(
        library_id=1,
        package="com.example:lib",
        platform="Android",
        current_version=current,
        latest_version=latest,
        **kwargs,
    )


class TestSemverComparisons:
    def test_newer_patch(self):
        r = _compare("1.0.0", "1.0.1")
        assert r.version_status == VersionStatus.NEWER
        assert r.new_version_released is True
        assert r.patch_bump is True
        assert r.major_bump is False

    def test_newer_minor(self):
        r = _compare("1.0.0", "1.1.0")
        assert r.version_status == VersionStatus.NEWER
        assert r.minor_bump is True
        assert r.major_bump is False

    def test_newer_major(self):
        r = _compare("1.5.0", "2.0.0")
        assert r.version_status == VersionStatus.NEWER
        assert r.major_bump is True

    def test_same_version(self):
        r = _compare("3.2.1", "3.2.1")
        assert r.version_status == VersionStatus.SAME
        assert r.new_version_released is False
        assert r.major_bump is False
        assert r.minor_bump is False
        assert r.patch_bump is False

    def test_older_version(self):
        r = _compare("5.0.0", "4.9.9")
        assert r.version_status == VersionStatus.OLDER
        assert r.new_version_released is False

    def test_carries_update_needed(self):
        r = _compare("1.0.0", "2.0.0", update_needed="Mandatory")
        assert r.update_needed == "Mandatory"

    def test_carries_library_status(self):
        r = _compare("1.0.0", "1.0.0", library_status="Deprecated")
        assert r.library_status == "Deprecated"


class TestNonSemverVersions:
    def test_internal_marker_stripped(self):
        # "55.0(internal)" → normalised → "55.0" compared to "4.16.0"
        r = _compare("55.0(internal)", "4.16.0")
        # 55.0 > 4.16.0 → OLDER (current is higher than latest)
        assert r.version_status == VersionStatus.OLDER

    def test_date_based_version(self):
        # e.g. "202407.1.0.0" vs "202601.2.5"
        r = _compare("202407.1.0.0", "202601.2.5")
        assert r.version_status == VersionStatus.NEWER

    def test_v_prefix_stripped(self):
        r = _compare("v1.0.0", "v2.0.0")
        assert r.version_status == VersionStatus.NEWER

    def test_viaspm_placeholder_is_unknown(self):
        r = _compare("ViaSPM", "6.17.9")
        assert r.version_status == VersionStatus.UNKNOWN
        assert r.needs_manual_review is True

    def test_not_in_podfile_is_unknown(self):
        r = _compare("NotinPodfile.lock", "202601.2.5")
        assert r.version_status == VersionStatus.UNKNOWN
        assert r.needs_manual_review is True

    def test_both_unknown_same_string(self):
        r = _compare("ViaSPM", "ViaSPM")
        # String equality → SAME
        assert r.version_status == VersionStatus.SAME

    def test_both_unknown_different_strings(self):
        r = _compare("ViaSPM", "NotinPodfile.lock")
        assert r.version_status == VersionStatus.UNKNOWN
        assert r.needs_manual_review is True

    def test_extracted_version_works(self):
        # "core-v7.1.7" → 7.1.7
        r = _compare("core-v7.1.7", "7.2.0")
        assert r.version_status == VersionStatus.NEWER
