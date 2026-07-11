# Engineering Standards and Phase 2 Plan

Date: 2026-06-30
Status: Active hardening plan (small, safe, E2E-verified changes)

## 1. What Is Already Implemented

### 1.1 SOLID (current baseline)

1. Single Responsibility Principle
- Microservices are split by capability (library-data, scraper, comparison, recommendation, notification, scheduler).
- Router -> Service -> Repository layering exists in backend services.

2. Open/Closed Principle
- Scraper strategy architecture supports adding registries with new strategy classes.

3. Liskov Substitution Principle
- Strategy interfaces and generator abstractions are used in recommendation/scraper implementations.

4. Interface Segregation Principle
- API schemas and service-specific DTOs exist for most paths.

5. Dependency Inversion Principle
- Services depend on repositories/abstractions rather than direct SQL in router layer for key flows.

### 1.2 Design Patterns in Use

1. Repository Pattern (ORM access isolation)
2. Service Layer Pattern (business logic centralization)
3. Strategy Pattern (scraper registries, recommendation generators)
4. Facade Pattern (API gateway as unified entry)
5. Pipeline Orchestration Pattern (scheduler steps)

### 1.3 Existing Hardening

1. Strict LLM output contract and fallback path in recommendation-service.
2. Global exception handlers in service entry points.
3. Pydantic schemas for request/response modeling.
4. Scheduler visibility with stage-level observability.

## 2. Gaps Still Present (and accepted for phased refactor)

1. Some UI pages still include domain decision display logic or ad-hoc error parsing.
2. Global exception typing is inconsistent across all services (some generic exceptions still leak to 500 path).
3. Naming/docstring consistency varies across modules.
4. Memory/thread-safety policy is implicit, not fully codified and documented per service.
5. Dependency management is mixed (requirements + pyproject) and not yet Poetry-locked uniformly.

## 3. Phase 2 — Small Change Sets (Non-breaking)

### Change Set A (completed)

1. Moved "set current version" business action from UI update logic to dedicated backend endpoint.
2. Added typed request/response models for that action.
3. Preserved behavior and E2E-verified.

### Change Set B (completed)

1. Added typed validation failure path for set-current-version flow.
2. Added global `ValidationError` -> HTTP 400 handler in library-data-service.
3. Added UI shared API error message parser and fixed interceptor rejection behavior.
4. Replaced ad-hoc page-level parsing in React `Libraries`, `Login`, and `Users` with shared parser usage.
5. Added detailed Python docstrings for core custom exceptions and exception handlers in library-data-service.

### Change Set C (next)

1. Standardize global exception response contract across all backend services.
2. Introduce shared error codes and mapping.
3. E2E verification for each service route group.

### Change Set D (next)

1. Introduce memory/performance guardrails for large response pages.
2. Ensure list endpoints support bounded pagination defaults and avoid over-fetch in UI.
3. Add thread-safety notes and immutable config handling where applicable.

### Change Set E (next)

1. Unify dependency management strategy.
2. Keep existing `requirements.txt` compatibility, add lock workflow and documented install policy.
3. Validate build and run path for all services.

## 4. Global Exception Handling Target Standard

All backend services should return this envelope on handled failures:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human readable message",
    "detail": null
  },
  "meta": {
    "service": "service-name",
    "version": "x.y.z"
  }
}
```

## 5. Thread Safety and Memory Optimization Policy (implementation target)

1. No mutable module-level state for request data.
2. Cache usage must be bounded with TTL and explicit invalidation strategy.
3. Batch endpoints must apply limits and chunking.
4. UI queries should use scoped cache keys and sensible stale times.
5. Avoid duplicate large payload transformation in render loops.

## 6. Verification Rule for Every Change Set

1. Static error check on modified files.
2. Full service restart.
3. E2E smoke: auth, key business endpoints, affected UI flow.
4. Regression sanity for recommendations and scheduler paths.
