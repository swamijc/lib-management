# Priority Classification Engine & HITL Approval Workflow

> **Scope:** Rule-based 4-tier priority logic + Human-in-the-Loop (HITL) approval flow,
> from initial library scan through recommendation generation, approval, and dashboard
> reflection.

---

## Table of Contents

1. [4-Tier Priority Classification](#1-4-tier-priority-classification)
   - 1.1 [Priority Levels](#11-priority-levels)
   - 1.2 [Classification Rules (ordered)](#12-classification-rules-ordered)
   - 1.3 [Rule 1 — Version Diff](#13-rule-1--version-diff)
   - 1.4 [Rule 2 — Keyword Scan of Release Notes](#14-rule-2--keyword-scan-of-release-notes)
   - 1.5 [Rule 3 — Merge (Always Take Higher)](#15-rule-3--merge-always-take-higher)
   - 1.6 [Rule 4 — SDK Sensitivity Floor](#16-rule-4--sdk-sensitivity-floor)
   - 1.7 [Special Pre-Rules](#17-special-pre-rules)
   - 1.8 [Complete Classification Flow with Examples](#18-complete-classification-flow-with-examples)
2. [HITL Approval Workflow](#2-hitl-approval-workflow)
   - 2.1 [What Triggers a HITL Entry](#21-what-triggers-a-hitl-entry)
   - 2.2 [HITL Lifecycle States](#22-hitl-lifecycle-states)
   - 2.3 [Approval Steps in the UI](#23-approval-steps-in-the-ui)
   - 2.4 [What Happens After Approval](#24-what-happens-after-approval)
3. [End-to-End Data Flow](#3-end-to-end-data-flow)
4. [Dashboard Reflection](#4-dashboard-reflection)
5. [Database Tables Involved](#5-database-tables-involved)

---

## 1. 4-Tier Priority Classification

### 1.1 Priority Levels

| Badge | Value | Meaning | Action Required |
|---|---|---|---|
| 🔴 **CRITICAL** | `critical` | Major version bump, CVE, deprecated library | Immediate — upgrade ASAP |
| 🟠 **HIGH** | `high` | Minor version bump, security fix, payment SDK | This sprint / next sprint |
| 🟡 **MODERATE** | `moderate` | Patch bump, bug fix, performance improvement | Backlog — next quarter |
| 🔵 **LOW** | `low` | Cosmetic, docs, minor cleanup | Optional / informational |
| ✅ **None** | `none` | Library is already up-to-date | No action needed |

---

### 1.2 Classification Rules (ordered)

The engine applies rules in this strict order. The **first rule that matches** wins for pre-conditions; the **highest priority** wins for scoring.

```
Pre-condition checks (return early)
  │
  ├─ Pre-Rule A: Deprecated library          → always CRITICAL (migration required)
  ├─ Pre-Rule B: Non-standard version string → Manual Review (no auto-priority)
  └─ Pre-Rule C: No new version available   → none (up-to-date)

4-Tier scoring (all three computed, then merged)
  │
  ├─ Rule 1: Version diff      → vp  (CRITICAL | HIGH | MODERATE)
  ├─ Rule 2: Keyword scan      → kp  (CRITICAL | HIGH | MODERATE | LOW)
  ├─ Rule 3: Merge(vp, kp)    → merged = max(vp, kp)
  └─ Rule 4: SDK sensitivity   → final = max(merged, sdk_baseline)
```

---

### 1.3 Rule 1 — Version Diff

Compares **semantic version** using `packaging.version.Version` (PEP 440).

| Version change | Result |
|---|---|
| `major` number increases | `CRITICAL` |
| `minor` number increases | `HIGH` |
| `patch` number increases | `MODERATE` |
| Same or cannot parse | `UP_TO_DATE` / `MODERATE` fallback |

**Code location:** `services/recommendation-service/src/generators/rule_based.py` → `_version_priority()`

**Examples:**

```
4.16.0  → 5.0.7    major: 4→5  → CRITICAL
33.16.0 → 34.13.0  major: 33→34 → CRITICAL
2.8.7   → 2.11.0   minor: 8→11  → HIGH
3.18.0  → 3.19.0   minor: 18→19 → HIGH
4.9.0   → 4.16.0   minor: 9→16  → HIGH
1.8.1   → 1.8.5    patch: 1→5   → MODERATE
```

---

### 1.4 Rule 2 — Keyword Scan of Release Notes

Scans the `release_notes` text for known keywords and assigns the **highest matched tier**.

| Tier | Keywords (partial list) |
|---|---|
| **CRITICAL** | `cve`, `vulnerability`, `critical`, `zero-day`, `remote code execution`, `rce`, `breaking change`, `incompatible`, `data breach`, `actively exploited` |
| **HIGH** | `security fix`, `security patch`, `authentication`, `authorization`, `payment`, `pci`, `gdpr`, `compliance`, `crash fix`, `memory leak`, `data loss`, `regression`, `deprecated`, `end of life`, `eol`, `3ds` |
| **MODERATE** | `bug fix`, `bugfix`, `fixed`, `improvement`, `performance`, `stability`, `api change`, `behaviour change`, `recommended` |
| **LOW** | `minor`, `cosmetic`, `typo`, `documentation`, `readme`, `refactor`, `cleanup`, `optional` |

**Code location:** `_keyword_priority()` and `_KEYWORD_RULES` dict

**Examples:**

```
"CVE-2026-1234 security fix patched"  → keywords: [cve, security fix]  → CRITICAL
"breaking change in analytics API"    → keywords: [breaking change]     → CRITICAL
"payment flow enhancement"            → keywords: [payment]             → HIGH
"bug fix and minor refactor"          → keywords: [bug fix, minor]      → MODERATE
""  (empty)                           → no match                        → LOW
```

---

### 1.5 Rule 3 — Merge (Always Take Higher)

```
merged_priority = max(version_priority, keyword_priority)
```

The merge uses this ordered scale:  `LOW < MODERATE < HIGH < CRITICAL`

**Examples:**

| Version Priority | Keyword Priority | Merged |
|---|---|---|
| HIGH (minor bump) | CRITICAL (cve in notes) | **CRITICAL** |
| CRITICAL (major bump) | LOW (no keywords) | **CRITICAL** |
| HIGH (minor bump) | LOW (no keywords) | **HIGH** |
| MODERATE (patch) | HIGH (security fix) | **HIGH** |

---

### 1.6 Rule 4 — SDK Sensitivity Floor

Some SDKs are security/payment-critical and always get a **minimum priority floor**,
regardless of the version bump size.

| SDK Floor | Libraries |
|---|---|
| **HIGH** | ACI OPPWa, ACI IPWorks, Braintree, PayPal, KlarnaMobileSDK, Gigya, GigyaAuth, GigyaTfa, SQLCipher |
| **MODERATE** | Firebase, FirebaseCrashlytics, FirebasePerformance, AppsFlyer, ContentsquareSDK, BlueTriangle |
| **LOW** | Alamofire, AFNetworking, Glide, SDWebImage, lottie-ios, Mantle |

```
final_priority = max(merged_priority, sdk_baseline)
```

**Example — Gigya PATCH bump elevated to HIGH:**

```
Gigya TFA:  1.0.14 → 1.0.15
  version_priority = MODERATE  (patch bump)
  keyword_priority = LOW        (no keywords)
  merged           = MODERATE
  sdk_baseline     = HIGH       (Gigya in sensitivity map)
  final            = HIGH       ← elevated by SDK rule
```

**Example — Alamofire MINOR bump stays HIGH (floor=LOW doesn't lower it):**

```
Alamofire:  5.9.1 → 5.12.0
  version_priority = HIGH     (minor bump)
  sdk_baseline     = LOW      (Alamofire floor)
  max(HIGH, LOW)   = HIGH     ← floor never lowers the priority
```

---

### 1.7 Special Pre-Rules

These run **before** the 4-tier scoring and exit early:

#### Pre-Rule A — Deprecated Library

If `library.status == "deprecated"`:
- Decision: **YES** (must upgrade/migrate)
- Priority written to DB: `critical`
- Summary: `[CRITICAL] {package} is deprecated — migration away from this library is required.`
- Version numbers are **irrelevant** — even `1.4.11 → 1.4.11` (same) triggers CRITICAL

**Example:**
```
Android Async HTTP  status=deprecated  cur=1.4.11  lat=1.4.11
→ [CRITICAL] com.loopj.android:android-async-http is deprecated — migration required.
```

#### Pre-Rule B — Non-Standard Version String

If `needs_manual_review == True` (version cannot be parsed):
- Decision: **NO** (do not auto-approve)
- Priority: unchanged (manual review badge in UI)
- Summary: `{package}: version '{cur}' is non-standard. Manual review required.`

**Example:**
```
OneTrust Publishers  cur="Not in Podfile.lock"  lat="202601.2.5"
→ Manual review required (version string is non-standard)
```

#### Pre-Rule C — Already Up-to-Date

If `new_version_released == False` or `cur == lat`:
- Decision: **SUFFICIENT**
- Priority in DB: `none`
- Summary: `{package} is up-to-date at version {cur}. No upgrade needed.`

---

### 1.8 Complete Classification Flow with Examples

#### Example 1 — `androidx.lifecycle:lifecycle-livedata` (HIGH)

```
Input:
  package  = "androidx.lifecycle:lifecycle-livedata"
  cur      = "2.8.7"
  lat      = "2.11.0"
  notes    = ""  (no release notes fetched)
  status   = "active"

Pre-Rule A? No (not deprecated)
Pre-Rule B? No (version is parseable)
Pre-Rule C? No (2.11.0 > 2.8.7, new version exists)

Rule 1 — Version diff:
  Version("2.8.7").minor = 8
  Version("2.11.0").minor = 11  → minor increased
  version_priority = HIGH

Rule 2 — Keyword scan:
  notes = ""  → no keywords matched
  keyword_priority = LOW

Rule 3 — Merge:
  max(HIGH, LOW) = HIGH

Rule 4 — SDK floor:
  "lifecycle-livedata" not in sensitivity map → baseline = LOW
  max(HIGH, LOW) = HIGH

Result:
  priority = HIGH
  Summary  = "[HIGH] androidx.lifecycle:lifecycle-livedata: 2.8.7 → 2.11.0 (minor version bump). Priority: HIGH"
  DB write = update_needed = "high"
```

#### Example 2 — `com.google.firebase:firebase-bom` (CRITICAL — major bump)

```
Input:
  package = "com.google.firebase:firebase-bom"
  cur     = "33.16.0"
  lat     = "34.13.0"
  notes   = "breaking change in analytics API"
  status  = "active"

Rule 1 — Version diff:
  33 → 34  (major increases)
  version_priority = CRITICAL

Rule 2 — Keyword scan:
  "breaking change" found → CRITICAL tier
  keyword_priority = CRITICAL

Rule 3 — Merge:
  max(CRITICAL, CRITICAL) = CRITICAL

Rule 4 — SDK floor:
  Firebase baseline = MODERATE → max(CRITICAL, MODERATE) = CRITICAL

Result:
  priority = CRITICAL
  Summary  = "[CRITICAL] com.google.firebase:firebase-bom: 33.16.0 → 34.13.0 (major version bump) — release notes: breaking change. Priority: CRITICAL"
```

#### Example 3 — `KlarnaMobileSDK` (HIGH — payment SDK floor)

```
Input:
  package = "KlarnaMobileSDK"
  cur     = "2.10.1"
  lat     = "2.11.4"
  notes   = "minor improvements to checkout flow"
  status  = "active"

Rule 1 — Version diff:
  2.10 → 2.11 (minor increases) → HIGH

Rule 2 — Keyword scan:
  "minor" found → LOW tier
  keyword_priority = LOW

Rule 3 — Merge:
  max(HIGH, LOW) = HIGH

Rule 4 — SDK floor:
  KlarnaMobileSDK baseline = HIGH
  max(HIGH, HIGH) = HIGH

Result:
  priority = HIGH
  Summary  = "[HIGH] KlarnaMobileSDK: 2.10.1 → 2.11.4 (minor version bump). Priority: HIGH"
```

#### Example 4 — `com.adobe.marketing.mobile:sdk-bom` (CRITICAL — keyword elevation)

```
Input:
  package = "com.adobe.marketing.mobile:sdk-bom"
  cur     = "3.18.0"
  lat     = "3.19.0"
  notes   = "CVE-2026-1234 security fix patched"
  status  = "active"

Rule 1 — Version diff:
  3.18 → 3.19 (minor) → HIGH

Rule 2 — Keyword scan:
  "cve" → CRITICAL,  "security fix" → HIGH
  keyword_priority = CRITICAL  (highest match wins)

Rule 3 — Merge:
  max(HIGH, CRITICAL) = CRITICAL  ← keyword elevated it!

Rule 4 — SDK floor:
  Not in map → baseline = LOW → max(CRITICAL, LOW) = CRITICAL

Result:
  priority = CRITICAL  (despite being only a minor bump!)
  Summary  = "[CRITICAL] com.adobe.marketing.mobile:sdk-bom: 3.18.0 → 3.19.0 (minor bump) — release notes: cve, security fix. Priority: CRITICAL"
```

---

## 2. HITL Approval Workflow

HITL (Human-in-the-Loop) is a **mandatory approval gate** before any library upgrade enters the deployment pipeline.

### 2.1 What Triggers a HITL Entry

Every time the pipeline's `batch_compare` step detects a **new version available**, it calls the lifecycle service to create or update a lifecycle entry with `status = awaiting_review`.

```
Pipeline Step 4 (batch_compare)
  ↓ new version detected for library
  ↓ POST /api/v1/lifecycle  { library_id, status: "awaiting_review" }
  ↓ Entry created in upgrade_lifecycle table
```

All 119 tracked libraries have a lifecycle entry. The HITL review page shows:
- **Default filter:** `🔴 Critical + High` (critical + high + legacy mandatory)
- **Per-item info:** package name, platform, version arrow, AI summary, pros/cons

### 2.2 HITL Lifecycle States

```
awaiting_review  →  Acknowledged  →  In Progress  →  Completed
                                                   ↘  Skipped
                                                   ↘  Rejected
```

| Status | Meaning | Who Sets It |
|---|---|---|
| `awaiting_review` | New version detected, waiting for human approval | Pipeline (automated) |
| `Acknowledged` | Engineer approved — upgrade queued for deployment | Admin via HITL UI |
| `In Progress` | Upgrade work has started | Admin (manual update) |
| `Completed` | Upgrade deployed, `current_version` updated in DB | Admin on completion |
| `Skipped` | Upgrade intentionally deferred | Admin via HITL UI |
| `Rejected` | Upgrade rejected (won't do) | Admin via HITL UI |

### 2.3 Approval Steps in the UI

**Location:** `http://localhost:3000/hitl-review`

1. **Filter** by priority (Critical+High / Critical only / High only / Moderate / All)
2. **Review** the AI summary, pros/cons, and version details for each library
3. **Optional:** enter a target version and deployment notes
4. **Click "Approve"** (single item) or **select multiple → "Approve All"** (bulk)

The approval sends:
```
PUT /api/v1/lifecycle/{lifecycle_id}
{
  "status": "Acknowledged",
  "actioned_by": "admin",
  "skip_reason": "...",         // optional deployment notes
  "target_version": "2.11.0"   // optional target version
}
```

### 2.4 What Happens After Approval

Approval triggers a **cascade of DB updates** across three tables:

#### Step 1 — Lifecycle status → `Acknowledged`

```sql
UPDATE upgrade_lifecycle
SET status = 'Acknowledged',
    actioned_by = 'admin',
    target_version = '2.11.0',
    skip_reason = 'Sprint 42 deployment',
    updated_at = NOW()
WHERE id = {lifecycle_id};
```

#### Step 2 — Audit log entry written

```sql
INSERT INTO library_update_log (
  library_id, field_changed, old_value, new_value,
  change_source, changed_by, changed_at
) VALUES (
  4, 'lifecycle_status', 'awaiting_review', 'Acknowledged',
  'hitl_approval', 'admin', NOW()
);
```

#### Step 3 — On `Completed` (upgrade deployed)

When the admin marks the lifecycle as `Completed` and provides `completed_version`:

```sql
-- 1. Update library current_version
UPDATE libraries
SET current_version = '2.11.0',
    update_needed   = 'none'
WHERE id = 4;

-- 2. Write audit log
INSERT INTO library_update_log (
  library_id, field_changed, old_value, new_value, ...
) VALUES (
  4, 'current_version', '2.8.7', '2.11.0', 'hitl_completion', 'admin', NOW()
);

-- 3. Close lifecycle entry
UPDATE upgrade_lifecycle
SET status = 'Completed',
    completed_version = '2.11.0',
    updated_at = NOW()
WHERE id = {lifecycle_id};
```

**Code location:** `services/library-data-service/src/routers/lifecycle.py` → `update_lifecycle()` (lines ~130–165)

---

## 3. End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SCHEDULED PIPELINE                           │
│                    (daily 02:00 UTC, or manual)                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  Step 1: fetch_libraries     │ Load all 119 libs from DB
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  Step 2: batch_scrape        │ Fetch latest_version from
              │                              │ registries (Maven, CocoaPods,
              │                              │ SPM, GitHub)
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  Step 3: fetch_version_      │ Get release notes from version
              │           history            │ history (used in keyword scan)
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  Step 4: batch_compare       │ Compare cur vs lat version
              │                              │ → sets new_version_released
              │                              │ → creates lifecycle entry if
              │                              │   newer version found
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  Step 5: batch_recommend     │ Run 4-tier classification:
              │                              │  Pre-Rule A: deprecated → CRITICAL
              │                              │  Pre-Rule B: non-standard → review
              │                              │  Pre-Rule C: up-to-date → none
              │                              │  Rule 1: version diff
              │                              │  Rule 2: keyword scan
              │                              │  Rule 3: merge (take higher)
              │                              │  Rule 4: SDK sensitivity floor
              │                              │
              │                              │ ► Writes update_needed to
              │                              │   libraries table
              │                              │ ► Stores summary in
              │                              │   recommendations table
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  Step 6: notify              │ Email / Teams webhook
              │                              │ (if channels configured)
              └──────────────┬──────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────┐
        │           HITL REVIEW PAGE             │
        │    http://localhost:3000/hitl-review   │
        │                                        │
        │  Engineer reviews Critical + High      │
        │  → Clicks "Approve"                    │
        └────────────────────┬───────────────────┘
                             │
             ┌───────────────▼────────────────┐
             │  PUT /api/v1/lifecycle/{id}     │
             │  { status: "Acknowledged" }     │
             └───────────────┬────────────────┘
                             │
       ┌─────────────────────▼──────────────────────┐
       │          upgrade_lifecycle table           │
       │  status: awaiting_review → Acknowledged    │
       └─────────────────────┬──────────────────────┘
                             │
             ┌───────────────▼────────────────┐
             │  Upgrade deployed by team      │
             │  Mark as Completed in UI       │
             │  Enter completed_version       │
             └───────────────┬────────────────┘
                             │
       ┌─────────────────────▼──────────────────────┐
       │              libraries table               │
       │  current_version: "2.8.7" → "2.11.0"      │
       │  update_needed:   "high"  → "none"         │
       └─────────────────────┬──────────────────────┘
                             │
                             ▼
        ┌──────────────────────────────────────────┐
        │           DASHBOARD (live)               │
        │  🔴 Critical: 27 → 26  (one resolved)    │
        │  ✅ Up to Date: 30 → 31                   │
        │  Risk score recalculates automatically   │
        └──────────────────────────────────────────┘
```

---

## 4. Dashboard Reflection

Once a lifecycle is marked **Completed** and `current_version` is updated, the dashboard
reflects the change on the **next page load / auto-refresh**.

### KPI Cards affected

| KPI Card | Before approval | After approval (Completed) |
|---|---|---|
| 🔴 Critical | 27 | 26 (decreases by 1) |
| ✅ Up to Date | 30 | 31 (increases by 1) |
| Risk Score % | e.g. 56% | Recalculates lower |
| HITL Pending | 119 | 118 |

### Risk Score Formula

```
risk_score = (critical × 3  +  high × 2  +  moderate × 1)
             ─────────────────────────────────────────────  × 100
                          total_libraries × 3
```

Example with current data:
```
risk_score = (27 × 3 + 57 × 2 + 4 × 1) / (119 × 3) × 100
           = (81 + 114 + 4) / 357 × 100
           = 199 / 357 × 100
           ≈ 56%
```

After resolving 1 CRITICAL:
```
risk_score = (26 × 3 + 57 × 2 + 4 × 1) / (119 × 3) × 100
           = (78 + 114 + 4) / 357 × 100
           ≈ 55%
```

---

## 5. Database Tables Involved

### `libraries` — master library record

| Column | Type | Updated by |
|---|---|---|
| `current_version` | TEXT | Lifecycle Completed event |
| `latest_version` | TEXT | Scraper (Step 2) |
| `update_needed` | TEXT | `batch_recommend` Step 5 writeback |
| `status` | TEXT | Admin manual edit |

### `recommendations` — AI/rule recommendation per library

| Column | Type | Updated by |
|---|---|---|
| `recommendation_summary` | TEXT | `batch_recommend` Step 5 |
| `upgrade_recommended` | TEXT | `batch_recommend` Step 5 (`Yes/No/Sufficient`) |
| `upgrade_pros` | JSON | `batch_recommend` Step 5 |
| `upgrade_cons` | JSON | `batch_recommend` Step 5 |

### `upgrade_lifecycle` — HITL approval tracking

| Column | Type | Updated by |
|---|---|---|
| `status` | TEXT | Pipeline (awaiting_review) / Admin (Acknowledged, Completed…) |
| `target_version` | TEXT | Admin during approval |
| `completed_version` | TEXT | Admin on completion |
| `actioned_by` | TEXT | Admin username |
| `skip_reason` | TEXT | Admin notes |

### `library_update_log` — full audit trail

Every change to `current_version`, `update_needed`, or lifecycle `status` is
recorded here with `old_value`, `new_value`, `changed_by`, and `changed_at`.

---

## Quick Reference — Priority Decision Table

```
╔══════════════════════╦══════════════╦═══════════════╦══════════════╗
║  Condition           ║ Version Bump ║ Keyword Match ║ Final Result ║
╠══════════════════════╬══════════════╬═══════════════╬══════════════╣
║ Library deprecated   ║ any          ║ any           ║ 🔴 CRITICAL  ║
║ Non-standard version ║ —            ║ —             ║ ⚠️  REVIEW   ║
║ No new version       ║ same         ║ —             ║ ✅ NONE       ║
╠══════════════════════╬══════════════╬═══════════════╬══════════════╣
║ Active library       ║ MAJOR bump   ║ any           ║ 🔴 CRITICAL  ║
║ Active library       ║ any          ║ cve/vuln      ║ 🔴 CRITICAL  ║
║ Active library       ║ MINOR bump   ║ no critical   ║ 🟠 HIGH      ║
║ Active library       ║ any          ║ security fix  ║ 🟠 HIGH      ║
║ Payment SDK          ║ any bump     ║ any           ║ 🟠 HIGH (min)║
║ Active library       ║ PATCH bump   ║ bug fix       ║ 🟡 MODERATE  ║
║ Gigya/SQLCipher      ║ PATCH bump   ║ any           ║ 🟠 HIGH (SDK)║
╚══════════════════════╩══════════════╩═══════════════╩══════════════╝
```

---

*Generated: 2026-06-30 | Services: recommendation-service v1.0 | rule_based.py*
