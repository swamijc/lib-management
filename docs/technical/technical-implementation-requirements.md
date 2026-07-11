# Library Management Application
## Technical Implementation Requirements (Freeze Baseline)

Document version: 2.0
Date: 2026-06-30
Status: Implemented baseline (current release)

## 1. Architecture Overview

The system is implemented as Python FastAPI microservices orchestrated by a scheduler, with a React frontend.

### Runtime Components

1. API Gateway (`:8000`)
- Auth, request routing, service boundary.

2. Library Data Service (`:8001`)
- Libraries, lifecycle, settings, LLM usage logging, persisted recommendations.

3. Scraper Service (`:8002`)
- Version and metadata retrieval from registries.

4. Comparison Service (`:8003`)
- Version comparison and change detection.

5. Recommendation Service (`:8004`)
- LLM generation with strict JSON contract and rule-based fallback.

6. Notification Service (`:8005`)
- Email/Teams notification dispatch.

7. Scheduler Service (`:8006`)
- Pipeline orchestration, schedule management, run history.

8. UI React (`:3000`)
- Business UI for dashboard, libraries, scheduler, governance, settings, users.

## 2. Pipeline Technical Requirement

Pipeline steps (canonical order):

1. fetch_libraries
2. batch_scrape
3. fetch_version_history
4. batch_compare
5. batch_recommend
6. notify

Technical requirements:

1. Run status persistence (`completed`, `failed`, `partial`, `running`).
2. Step-level metadata: message, duration, items processed, timestamps.
3. SLA visibility per step in UI with target thresholds.
4. Dedicated failure root-cause summary for latest failed/partial run.

## 3. Recommendation and LLM Requirements

1. LLM output contract must be strict structured JSON.
2. Parser must validate required fields and fallback safely when invalid.
3. Prompt templates must be editable in backend settings UI.
4. LLM usage metrics must be logged with tokens/cost/latency.
5. Runtime mode must be visible: AI Active vs fallback mode.

## 4. Data and Read/Write Path Requirements

1. Recommendations displayed to users must be read from persisted data source.
2. Recommendation generation and recommendation read routes must be separated if needed to avoid stale runtime cache reads.
3. Library current version update actions from Version History must invalidate related UI query caches.

## 5. UI Requirements (Implemented)

### Dashboard
1. Show high-level LLM usage panel (calls, tokens, cost, mode, avg latency).
2. Keep KPI and operational overview cards.

### Libraries
1. Table alignment must be stable and business-readable.
2. Library details section must be organized as Business View + Technical View + Notes.
3. Version History must support setting selected version as current active version.

### Scheduler
1. Section grouping: Control, Runtime Health, Current Run, Run History.
2. Stage-by-stage SLA indicator and outcome badge.
3. Top strip for latest failure root cause.
4. LLM runtime configuration visibility.

### Analytics
1. Navigation and page naming: "LLM Analytics".
2. Show model/calls/tokens/cost/latency trends and recent usage.

## 6. Non-Functional Requirements

1. No documentation/folder organization change may alter runtime behavior.
2. Maintain service restart operability via `manage.sh`.
3. Maintain compatibility with existing SQLite schema.
4. Keep UI responsive on desktop and common laptop viewport sizes.

## 7. Operational Verification Checklist

1. UI loads all key pages without runtime errors.
2. Scheduler run can be triggered and tracked end-to-end.
3. Recommendation rows persist and display in Libraries page.
4. LLM analytics endpoint returns expected aggregates.
5. Version history "set as current" updates current version and reflects immediately.

## 8. Folder Organization Baseline

Documentation folder organization is standardized as:

- `docs/requirements/business-requirements-and-frs.md`
- `docs/technical/technical-implementation-requirements.md`
- `docs/archive/*` for superseded drafts

This reorganization is documentation-only and does not impact executable code paths.
