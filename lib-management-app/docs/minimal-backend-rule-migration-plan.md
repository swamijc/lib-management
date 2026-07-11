# Minimal Backend Rule Migration Plan (No UI API Break)

## Objective
Move only high-risk business rules from frontend to backend first:
1. Portfolio risk score and priority aggregation
2. HITL confidence scoring
3. Operational thresholds and policy drift rules
4. SLA forecasting risk calculations

Keep existing API paths and existing response keys working during migration.

## Current High-Risk Rules in Frontend
- Dashboard page:
  - Priority bucket logic and weighted risk score
  - SLA forecast and projected risk counts
  - Ownership balancing suggestions
- HITL Review page:
  - Confidence scoring and confidence banding
- Governance page:
  - Business critical classification and overdue/due-soon logic
- Settings page:
  - Runtime thresholds and policy drift alert generation

## Compatibility Strategy
Use additive response changes only.
- Do not remove current fields.
- Add new computed fields under a backend section.
- Frontend reads backend fields first, then uses existing local calculation as fallback.
- Remove fallback only after stability window.

## Phase 0: Contract and Feature Flag
Duration: 1 to 2 days

1. Add a backend feature flag:
- Name: use_backend_business_rules
- Default: false in all environments

2. Define response extension model (additive):
- Dashboard sources:
  - risk_score
  - priority_counts
  - sla_forecast
  - ownership_balance_summary
- HITL lifecycle payload:
  - confidence_score
  - confidence_band
- Settings runtime payload:
  - threshold_alerts
  - policy_drift_alerts
  - policy_drift_summary

3. Add telemetry counters:
- backend_rule_eval_success_total
- backend_rule_eval_fallback_total
- backend_rule_eval_latency_ms

Exit criteria:
- Backend can produce fields behind feature flag.
- Existing clients unaffected.

## Phase 1: Backend Compute (No Frontend Switch Yet)
Duration: 2 to 4 days

1. Implement backend rule module:
- Module structure:
  - rules/risk.py
  - rules/hitl_confidence.py
  - rules/policy_drift.py
  - rules/sla_forecast.py

2. Wire rule outputs into existing endpoints:
- Keep same endpoints.
- Add computed blocks in data payload.

3. Add deterministic unit tests:
- Priority mapping edge cases
- Empty dataset behavior
- Threshold boundaries
- Date/time handling for SLA and overdue windows

Exit criteria:
- Rule outputs available in responses.
- 80%+ unit coverage for rule modules.

## Phase 2: Frontend Read-Through (Safe Fallback)
Duration: 1 to 2 days

1. Frontend update pattern:
- For each rule output:
  - Use backend field when present.
  - Fallback to existing frontend computation when missing.

2. Pages to update first:
- Dashboard
- HITL Review
- Settings

3. Add console/dev warning in non-production when fallback is used.

Exit criteria:
- No UI regression.
- Existing pages render even if backend flag is off.

## Phase 3: Cutover and Cleanup
Duration: 1 to 2 days

1. Enable flag in staging.
2. Compare frontend legacy output vs backend output for 3 to 5 days.
3. Enable in production gradually:
- 10% traffic
- 50% traffic
- 100% traffic

4. Remove duplicated frontend formulas after stable window.

Exit criteria:
- No parity drift for agreed metrics.
- Frontend business formulas removed from migrated areas.

## Minimal Endpoint Extension Sketch
1. SLA summary endpoint:
- Add:
  - risk_score
  - priority_counts
  - forecast: { d7, d14, d30, throughput_per_day }

2. Lifecycle listing and pending review endpoints:
- Add per item:
  - confidence_score
  - confidence_band
  - business_critical boolean

3. Health/runtime endpoint:
- Add:
  - threshold_alerts array
  - policy_drift_alerts array
  - policy_drift_summary object

## Rollback Plan
- Toggle feature flag off.
- Frontend fallback remains active.
- No endpoint rollback required because additions are backward compatible.

## Ownership
- Backend owner: API/service team
- Frontend owner: UI React team
- QA owner: Integration and parity verification

## Acceptance Checklist
- Additive schema only
- No existing field removed or renamed
- Frontend fallback present in first release
- Rule module unit tests passing
- Staging parity report signed off
- Production rollout with monitoring and rollback toggle ready
