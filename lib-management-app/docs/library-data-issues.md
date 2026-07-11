# Library Table — Data Quality Issues Report

**Date:** 2026-07-01  
**Total libraries audited:** 119  
**Total issues found:** 26 across 20 libraries  

---

## CATEGORY 1 — VERSION STORED AS TEXT / NOT A REAL VERSION (2 issues)

### Issue 1.1 — `current_version` is not a semver

| Field | Value |
|---|---|
| **Library ID** | 111 |
| **SDK Name** | OneTrust Publishers Headless SDK |
| **Platform** | iOS |
| **Field** | `current_version` |
| **Bad value** | `"Not in Podfile.lock"` |
| **Latest version** | `202601.2.5` |

**Error:** `current_version` contains a prose description, not a version number. This breaks version comparison, priority calculation, and scraper logic.

**Fix:**  
Set `current_version` to the actual installed version from your Podfile.lock.  
If unknown, set to `null` or `"unknown"` and mark `update_needed = "none"` until verified.

```
PUT /api/v1/libraries/111
{ "current_version": "<actual version from Podfile.lock>", "updated_by": "admin" }
```

---

### Issue 1.2 — `current_version` is a placeholder, not a semver

| Field | Value |
|---|---|
| **Library ID** | 119 |
| **SDK Name** | FlightLog (SPM) |
| **Platform** | iOS |
| **Field** | `current_version` |
| **Bad value** | `"ViaSPM"` |
| **Latest version** | `null` (not scraped) |

**Error:** `current_version = "ViaSPM"` is a placeholder indicating the version is managed by Swift Package Manager. No actual version is stored. Cannot compare versions or calculate priority.

**Fix:**  
Look up the actual resolved version in your `.package.resolved` or Xcode project.  
Set both `current_version` and `latest_version` to real semver strings.

```
PUT /api/v1/libraries/119
{ "current_version": "<real semver>", "latest_version": "<latest from registry>", "updated_by": "admin" }
```

---

## CATEGORY 2 — `latest_version` MISSING / NOT SCRAPED (2 issues)

### Issue 2.1 — `latest_version` is null (private/internal registry)

| Field | Value |
|---|---|
| **Library ID** | 33 |
| **SDK Name** | Iovation SDK |
| **Platform** | Android |
| **Registry** | Maven/mvnrepository.com |
| **current_version** | `5.3.0` |
| **latest_version** | `""` (empty) |
| **repo_url** | `https://mvnrepository.com/artifact/com.iovation/iovation-sdk` |

**Error:** Scraper returns 422 for this library (private registry — not publicly accessible on Maven Central). `latest_version` is never populated, so upgrade comparison cannot run.

**Fix:**  
Option A — Manually set `latest_version` to the known current release:
```
PUT /api/v1/libraries/33
{ "latest_version": "5.3.0", "update_needed": "none", "updated_by": "admin" }
```
Option B — Change `registry` to `"internal"` to exclude from auto-scraping.

---

### Issue 2.2 — `latest_version` is null (SPM — no scraper support)

| Field | Value |
|---|---|
| **Library ID** | 119 |
| **SDK Name** | FlightLog (SPM) |
| **Platform** | iOS |
| **Registry** | `spm` |
| **current_version** | `"ViaSPM"` |
| **latest_version** | `null` |
| **repo_url** | `null` |

**Error:** No scraper strategy exists for this SPM package. Both `latest_version` and `repo_url` are missing. Priority calculation returns `none` by default.

**Fix:**  
Set `repo_url` to the GitHub URL of the Swift package and `latest_version` manually:
```
PUT /api/v1/libraries/119
{ "repo_url": "https://github.com/<owner>/<repo>", "latest_version": "<latest tag>", "updated_by": "admin" }
```

---

## CATEGORY 3 — `repo_url` MALFORMED (8 issues)

All 8 libraries below have `repo_url` set to a partial name or package path instead of a full `https://` URL. This means:
- Release notes cannot be fetched from GitHub
- The URL link in the UI is broken
- Scraper cannot follow the URL for version history

### Issue 3.1

| ID | SDK | Bad `repo_url` | Correct URL |
|---|---|---|---|
| 3 | Lifecycle Runtime KTX | `"lifecycle-"` | `https://github.com/androidx/androidx/tree/main/lifecycle` |

### Issue 3.2

| ID | SDK | Bad `repo_url` | Correct URL |
|---|---|---|---|
| 21 | Facebook Shimmer | `"shimmer-android"` | `https://github.com/facebookarchive/shimmer-android` |

### Issue 3.3

| ID | SDK | Bad `repo_url` | Correct URL |
|---|---|---|---|
| 27 | Google Flexbox Layout | `"flexbox-layout"` | `https://github.com/google/flexbox-layout` |

### Issue 3.4

| ID | SDK | Bad `repo_url` | Correct URL |
|---|---|---|---|
| 28 | Gigya Android SDK | `"gigya-android-sdk"` | `https://github.com/SAP/gigya-android-sdk` |

### Issue 3.5

| ID | SDK | Bad `repo_url` | Correct URL |
|---|---|---|---|
| 29 | Gigya Android TFA | `"gigya-android-tfa"` | `https://github.com/SAP/gigya-android-sdk` (same repo) |

### Issue 3.6

| ID | SDK | Bad `repo_url` | Correct URL |
|---|---|---|---|
| 43 | Play Services Auth | `"play-services-auth"` | `https://github.com/googleapis/google-api-java-client-services` |

### Issue 3.7

| ID | SDK | Bad `repo_url` | Correct URL |
|---|---|---|---|
| 71 | ContentSquare Android SDK | `"Sdk"` | `https://github.com/ContentSquare/android-sdk` (verify with vendor) |

### Issue 3.8

| ID | SDK | Bad `repo_url` | Correct URL |
|---|---|---|---|
| 73 | ContentSquare Crash Reporter | `"com.contentsquare.error.analysis.crash"` | `https://github.com/ContentSquare/android-sdk` (verify with vendor) |

**Fix for all repo_url issues:**  
Edit each library in the SDK Portfolio page → Info tab → Repository URL field.  
Or use the API:
```
PUT /api/v1/libraries/{id}
{ "repo_url": "https://github.com/<correct-path>", "updated_by": "admin" }
```

---

## ADDITIONAL OBSERVATIONS (not bugs, but worth reviewing)

| ID | SDK | Observation |
|---|---|---|
| 21 | Facebook Shimmer | `status = "Deprecated"` but `update_needed = "critical"`. If deprecated, consider setting `update_needed = "none"` and documenting a replacement library. |
| 28 | Gigya Android SDK | `current_version = "core-v7.1.7"` — version has a `core-v` prefix which differs from standard semver. Scraper may not parse comparisons correctly. Verify actual version string from Maven. |
| 33 | Iovation SDK | `status = "Unknown"` — should be set to Active or Inactive explicitly. |
| 111 | OneTrust SDK | `latest_version = "202601.2.5"` — uses date-based versioning (year+patch). Priority shows "moderate". If this is correct, it is fine; if not, verify with vendor. |

---

## CATEGORY 4 — SDKs WITH NO VERSION HISTORY (impact on UI + workflow)

### What happens when Version History is empty

When a user opens the **📦 Version History** tab for an SDK that has never been scraped (or cannot be scraped), the following problems occur:

| Component | What breaks |
|---|---|
| Version History list | Shows "No versions fetched yet" — user cannot click "Select for Review" |
| "Select for Review" button | Does not appear — **upgrade review workflow cannot start** |
| In Progress Ver. column | Shows "—" even if a lifecycle exists with a target_version |
| Recommendation rationale | May show stale or no release notes comparison |
| Priority calculation | Stays at whatever was last set manually — no automatic update |

### Affected libraries — 7 SDKs with empty or useless version history

| ID | SDK | Platform | Registry | Reason history is empty |
|---|---|---|---|---|
| 33 | Iovation SDK | Android | maven | Private registry — scraper returns 422 |
| 88 | AFNetworking | iOS | cocoapods | `current_version = "55.0(internal)"` — internal build, no registry version |
| 96 | Encrypted Core Data | iOS | custom | `current_version = "55.0(internal)"` — internal build |
| 106 | Iovation Custom SDK | iOS | custom | Internal SDK with no public registry |
| 115 | SQLCipher | iOS | custom | `current_version = "55.0(internal)"` — internal build |
| 118 | AppsFlyer iOS (SPM) | iOS | spm | SPM — no scraper strategy |
| 119 | FlightLog (SPM) | iOS | spm | SPM — no scraper strategy, no repo_url |

### Root cause — `"55.0(internal)"` placeholder

Libraries 88, 96, 106, and 115 all have `current_version = "55.0(internal)"`. This appears to be a bulk import artefact where a placeholder was inserted for libraries managed via internal/vendor builds.

**Effect on version history:**
- The scraper fetches versions but they will never match `"55.0(internal)"` as "Current"
- The "Current Active" button will never show in the version list
- Priority comparison between `"55.0(internal)"` and a real semver is undefined

### Fix per category

#### Fix A — Internal / private SDKs (88, 96, 106, 115)
These SDKs are not versioned via public registries. Set them explicitly:
```
PUT /api/v1/libraries/{id}
{
  "current_version": "<actual internal version e.g. 7.1.7>",
  "latest_version": "<known latest from vendor>",
  "registry": "internal",
  "update_needed": "none",
  "updated_by": "admin"
}
```
Setting `registry = "internal"` tells the scraper to skip them. Version history tab will show "No versions fetched yet" but this is intentional for internal SDKs.

#### Fix B — SPM SDKs (118, 119)
SPM packages resolve versions via `Package.resolved`. Set manually:
```
PUT /api/v1/libraries/118
{
  "current_version": "<resolved version from .package.resolved>",
  "registry": "github",
  "repo_url": "https://github.com/AppsFlyerSDK/AppsFlyerFramework",
  "updated_by": "admin"
}

PUT /api/v1/libraries/119
{
  "current_version": "<resolved version>",
  "latest_version": "<latest tag>",
  "repo_url": "https://github.com/<owner>/<repo>",
  "registry": "github",
  "updated_by": "admin"
}
```
Once `registry = "github"` and `repo_url` is set, the GitHub scraper strategy can fetch version history.

#### Fix C — Private Maven (33)
Already documented in Issue 2.1 above. Set `registry = "internal"` to stop scraper attempts.

---

## CATEGORY 5 — SDKs ON CUSTOM/UNSUPPORTED REGISTRIES (12 SDKs)

The following SDKs use registries where no automatic scraper strategy exists. Version history will **always be empty** unless manually maintained.

| ID | SDK | Registry | Has latest? | Impact |
|---|---|---|---|---|
| 75 | ACI IPWorks 3DS SDK | custom | ✅ manual | Version history fetch always fails — "Fetch Versions" button does nothing |
| 76 | ACI OPPWa Mobile SDK | custom | ✅ manual | Same as above |
| 88 | AFNetworking | cocoapods | ❌ internal | Version shows "55.0(internal)" — no scraping |
| 91 | BlueTriangle Swift SDK | github | ✅ | GitHub strategy should work if `repo_url` is correct |
| 93 | CS Crash Reporter | github | ✅ same | GitHub strategy should work |
| 94 | Swift Protobuf | github | ✅ | GitHub strategy should work |
| 96 | Encrypted Core Data | custom | ❌ internal | No scraping — internal build |
| 106 | Iovation Custom SDK | custom | ✅ manual | No `repo_url` — version history fetch fails entirely |
| 111 | OneTrust Headless SDK | custom | ✅ manual | Fetch may work if `repo_url` is valid GitHub URL |
| 112 | PayPal iOS SDK | github | ✅ | GitHub strategy should work |
| 115 | SQLCipher | custom | ❌ internal | No scraping — internal build |
| 118 | AppsFlyer iOS (SPM) | spm | ✅ manual | No SPM scraper — set to github registry to enable |
| 119 | FlightLog (SPM) | spm | ❌ | No SPM scraper + no repo_url — completely dark |

### UI behaviour when "Fetch Versions" fails

When a user clicks **Fetch Versions** for any of the above:
- The request goes to the scraper-service
- Scraper finds no matching strategy → returns empty results or 422
- Version History panel stays empty: "No versions fetched yet"
- "Select for Review" button never appears
- Upgrade Review Queue cannot be opened via the version panel
- User is **stuck** — cannot start the approval workflow from the UI

### Workaround for stuck workflows

If version history cannot be fetched but a lifecycle review is still needed:
1. An admin can directly create/update the lifecycle via the API:
```
POST /api/v1/lifecycle
{ "library_id": <id>, "actioned_by": "admin", "target_version": "<version>" }
```
2. The Upgrade Review Queue will then auto-show in the expanded library row (since lifecycle status becomes In Progress or similar)
3. The full Acknowledge → In Progress → Set Active flow works even without version history

---

## Summary Table

| # | Library ID | SDK Name | Issue Type | Severity |
|---|---|---|---|---|
| 1 | 111 | OneTrust Publishers Headless SDK | current_version = prose text | 🔴 High |
| 2 | 88 | AFNetworking | current_version = `"55.0(internal)"` | 🔴 High |
| 3 | 96 | Encrypted Core Data | current_version = `"55.0(internal)"` | 🔴 High |
| 4 | 106 | Iovation Custom SDK | current_version = `"55.0(internal)"` | 🔴 High |
| 5 | 115 | SQLCipher | current_version = `"55.0(internal)"` | 🔴 High |
| 6 | 118 | AppsFlyer iOS (SPM) | current_version = `"ViaSPM"` | 🔴 High |
| 7 | 119 | FlightLog (SPM) | current_version = `"ViaSPM"` + no latest + no repo | 🔴 High |
| 8 | 33 | Iovation SDK | latest_version missing — private registry | 🟠 Medium |
| 9 | 75 | ACI IPWorks 3DS SDK | Custom registry — version history always empty | 🟠 Medium |
| 10 | 76 | ACI OPPWa Mobile SDK | Custom registry — version history always empty | 🟠 Medium |
| 11 | 91 | BlueTriangle Swift SDK | github registry — verify repo_url works | 🟡 Low |
| 12 | 93 | CS Crash Reporter | github registry — verify repo_url works | 🟡 Low |
| 13 | 94 | Swift Protobuf | github registry — verify repo_url works | 🟡 Low |
| 14 | 112 | PayPal iOS SDK | github registry — verify repo_url works | 🟡 Low |
| 15 | 3 | Lifecycle Runtime KTX | repo_url malformed | 🟡 Low |
| 16 | 21 | Facebook Shimmer | repo_url malformed | 🟡 Low |
| 17 | 27 | Google Flexbox Layout | repo_url malformed | 🟡 Low |
| 18 | 28 | Gigya Android SDK | repo_url malformed + version prefix `core-v` | 🟡 Low |
| 19 | 29 | Gigya Android TFA | repo_url malformed | 🟡 Low |
| 20 | 43 | Play Services Auth | repo_url malformed | 🟡 Low |
| 21 | 71 | ContentSquare Android SDK | repo_url malformed | 🟡 Low |
| 22 | 73 | ContentSquare Crash Reporter | repo_url malformed | 🟡 Low |
| 23 | 106 | Iovation Custom SDK | No repo_url — version history fetch entirely broken | 🟠 Medium |
| 24 | 21 | Facebook Shimmer | status=Deprecated but update_needed=critical | 🟡 Low |
| 25 | 33 | Iovation SDK | status=Unknown — should be Active or Inactive | 🟡 Low |
| 26 | 111 | OneTrust SDK | Date-based versioning — verify with vendor | 🟡 Low |
