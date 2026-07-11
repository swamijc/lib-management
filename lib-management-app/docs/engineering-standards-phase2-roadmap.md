# Engineering Standards Phase 2 Roadmap

Date: 2026-06-30
Status: Active hardening (Sets A and B completed)
Scope: Entire codebase (`services/*`, `shared/*`, `services/ui-react/*`)

## 1. What Is Missing Today (Observed)

1. SOLID consistency is partial
- Strong in repository/service split in backend, but some domain logic still appears in UI pages.

2. Design patterns are present but not consistently documented
- Strategy/Repository/Facade/Chain exist, but no single engineering standards reference was enforcing these.

3. Global exception handling is inconsistent by service
- Generic handlers exist, but domain-specific exception mapping is incomplete in some flows.

4. API contract consistency gaps
- Some endpoints use typed DTOs well, others rely on loose dict payloads.

5. Naming/docstring consistency
- Mixed naming style and inconsistent method-level docstrings in some modules.

6. Memory/thread-safety/performance hardening
- No explicit documented policy for cache bounds, concurrency controls, and object lifecycle.

7. Security hardening baseline
- Core auth and service-key controls exist, but no centralized policy checklist for secrets, payload limits, and endpoint risk profile.

8. Dependency management governance
- Multiple service-level `requirements.txt` + `pyproject.toml` exist, but no single unified dependency governance process.

## 2. Phase 2 Principles (Non-Breaking)

1. Small change sets only.
2. Preserve public API behavior unless explicitly approved.
3. E2E verify each change set.
4. Prioritize high-risk paths (recommendations, scheduler, settings, auth, library mutations).

## 3. What We Can Implement for Entire Codebase

## 3.1 SOLID and Layering Enforcement

1. UI layer
- Keep UI as presentation + orchestration only.
- No business decisions/classification logic in pages.
- Introduce service-style UI helpers where needed.

2. Backend layer
- Continue service layer ownership of business rules.
- Router = input/output boundary only.
- Repository = persistence only.

3. Interface segregation
- Narrow request/response DTO per endpoint (Pydantic).
- Avoid generic `object` payloads in typed frontend API methods.

## 3.2 Design Pattern Standardization

1. Strategy pattern
- Scraper strategies and recommendation strategies stay isolated and plugin-friendly.

2. Repository + Unit-of-Work
- All DB writes through repository/service methods.

3. Facade/API Gateway
- Keep routing concerns separate from service internals.

4. Chain/Orchestration
- Scheduler pipeline steps maintain explicit order and typed step state.

5. Template method
- Notification formatting and recommendation prompt composition should stay template-driven.

## 3.3 Global Exception Handling (Backend + UI)

1. Backend
- Introduce/expand domain exceptions (`*_NotFound`, validation, conflict, external failure).
- Map each domain exception to deterministic HTTP status + standard error envelope.
- Ensure every service has a global fallback handler for unknown exceptions.

2. UI
- Normalize API error shape in one place (API client).
- Avoid repeated ad-hoc error parsing in page components.

## 3.4 API Standard and Pydantic Contracts

1. Every mutating endpoint should have:
- Request DTO
- Response DTO
- Field descriptions and constraints

2. Optional: adopt strict model config for critical payloads.

3. Ensure response envelope remains consistent across services.

## 3.5 Naming and Docstring Standard

1. Python
- Use clear verbs in service methods (`set_current_active_version`, `generate_batch`).
- Add concise docstrings for public methods and non-trivial internal logic.

2. UI/TS
- Use explicit intent names (`setCurrentVersion`, `fetchVersions`).
- Keep one responsibility per component section.

## 3.6 Memory and Performance Optimization

1. Backend
- Bound in-memory caches with TTL + max size where relevant.
- Avoid loading large result sets without pagination.
- Reuse clients where safe and practical.

2. UI
- Keep query cache/stale-time explicit per data volatility.
- Remove expensive derived logic from render path where possible.

## 3.7 Thread-Safety / Concurrency Safety

1. Async services
- Avoid mutable shared global state without lock/guard.
- Use per-request objects for mutable data.
- Guard batch/concurrent operations with semaphore limits.

2. Scheduler
- Prevent duplicate active runs and maintain idempotent step transitions.

## 3.8 Security Hardening

1. Enforce service-key checks on internal endpoints.
2. Standardize redaction for secrets in logs.
3. Add payload size limits and validation for high-risk endpoints.
4. Continue JWT and role-based checks on admin mutation routes.

## 3.9 Dependency Governance

1. Keep service-local dependencies isolated.
2. Define approved versions and update cadence.
3. Optional staged migration plan to Poetry lock standard per service (non-breaking rollout).

## 4. Phase 2 Execution Backlog (Small E2E Sets)

Set A (Completed in this phase)
1. Move version-history set-current business logic to backend endpoint.
2. Add typed DTOs for set-current API.
3. Remove hardcoded recommendation decision engine from UI fallback.
4. Add domain exception mapping for invalid version selection.

Set B (Completed in this phase)
1. Centralize UI API error normalization.
2. Replace repeated page-level error parsing patterns.
3. Add `ValidationError` -> HTTP 400 mapping in library-data-service.
4. Replace ad-hoc parsing in React pages (`Libraries`, `Login`, `Users`) with shared API parser.

Set C
1. Add/standardize domain exceptions in recommendation/scheduler settings critical routes.
2. Add deterministic status mappings (404/409/422).

Set D
1. Introduce endpoint DTO tightening for remaining generic object payloads.
2. Add docstring pass for critical services.

Set E
1. Cache/memory policy docs + bounded cache implementation where required.
2. Concurrency audit and semaphore/guard updates where needed.

Set F
1. Security hardening checklist implementation and validation.
2. Dependency governance documentation and rollout process.

## 5.1 Latest Verification Snapshot (2026-06-30)

1. Static checks
- No errors in touched backend and frontend files for Change Set B.

2. Service restart
- Full stack restart successful across all services.

3. E2E smoke (set-current-version)
- Positive path: successful current-version update.
- Negative path 1: unknown version -> `404 VERSION_NOT_FOUND`.
- Negative path 2: whitespace-padded version -> `400 VALIDATION_ERROR`.
- Recommendation read path remained healthy (5949 rows at validation time).

## 5. Verification Template per Set

1. Static checks (type/errors) on touched files.
2. Service restart.
3. E2E API smoke for impacted flows.
4. UI smoke for impacted pages.
5. Regression check for recommendations + scheduler + libraries core paths.

---

This roadmap is intended to be executed incrementally to preserve stability while raising engineering standards across the full stack.
