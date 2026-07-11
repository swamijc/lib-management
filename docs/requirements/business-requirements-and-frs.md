# Library Management Application
## Business Requirements and Functional Requirements (Freeze Baseline)

Document version: 2.0
Date: 2026-06-30
Status: Baseline frozen for current release

## 1. Business Objective

Create one organization-wide platform to:

1. Track libraries used in Android and iOS applications.
2. Detect newer versions from external registries.
3. Generate upgrade guidance with business-friendly rationale.
4. Support Human-in-the-Loop (HITL) approval for important changes.
5. Notify stakeholders through email and Teams on schedule.

## 2. Current In-Scope Business Features

1. Centralized library inventory and governance dashboard.
2. Automated version lookup and comparison pipeline.
3. Priority classification (critical/high/moderate/low/none) and decision guidance.
4. LLM-assisted recommendation generation with strict JSON contract and rule-based fallback.
5. HITL review workflow for actionable upgrades.
6. Scheduler with run history, step status, SLA visibility, and failure root-cause strip.
7. Notifications (email and Teams) with configurable channels.
8. Admin settings for LLM, prompts, and application controls.
9. LLM analytics (usage, tokens, latency, cost) and high-level dashboard summary.

## 3. Out of Scope (Current Release)

1. Automatic code upgrade in consuming mobile apps.
2. Multi-ecosystem registries beyond current Android/iOS focus as default production path.
3. Full enterprise SSO integration.
4. Deep CI/CD policy enforcement automation in this release.

## 4. Core User Roles

1. Admin
- Configure scheduler, notifications, LLM settings, and prompt templates.
- Manage libraries and user-level settings.
- Trigger manual pipeline runs.

2. Viewer/Reviewer
- View dashboard, library state, recommendations, and run outcomes.
- Participate in HITL review where enabled.

## 5. Functional Requirement Baseline

### FR-01 Library Management
- System shall list, add, edit, deactivate/reactivate, and delete libraries.
- System shall show business and technical details per library.

### FR-02 Version Discovery
- System shall fetch version history and latest versions from supported sources.
- System shall allow setting a selected historical version as current active version.

### FR-03 Version Comparison and Classification
- System shall compare current vs latest and classify urgency.
- System shall persist comparison/recommendation outcomes.

### FR-04 Recommendation Generation
- System shall generate recommendation output in structured format.
- System shall support LLM path and rule-based fallback when LLM is unavailable.

### FR-05 Scheduler and Pipeline Visibility
- System shall execute pipeline steps in sequence.
- System shall show live status, stage outcomes, and run history.
- System shall show stage-level SLA indicators and highlight failure root cause.

### FR-06 HITL Workflow
- System shall create and manage review lifecycle entries.
- System shall support approval/rejection/acknowledgement actions.

### FR-07 Notifications
- System shall deliver notifications to configured channels (email, Teams).
- System shall preserve notification logs/status.

### FR-08 LLM Settings and Prompt Governance
- System shall allow configuring provider/model/key and prompt templates.
- Prompt templates shall be editable via UI and stored server-side.

### FR-09 Analytics
- System shall expose LLM usage metrics (calls, tokens, cost, latency).
- UI shall present LLM Analytics and dashboard high-level usage summary.

## 6. Acceptance Criteria (Release Freeze)

1. Dashboard shows library health, scheduler stats, and high-level LLM usage.
2. Libraries page has aligned table layout and business-first detail organization.
3. Version History supports selecting and setting an intermediate version as current active version.
4. Scheduler page grouped as Control, Runtime Health, Current Run, Run History.
5. Scheduler shows stage-by-stage SLA status and top failure root-cause strip.
6. Navigation and page naming use "LLM Analytics".
7. Recommendation read path uses persisted DB-backed records.
8. No runtime service behavior is broken by documentation/folder updates.

## 7. Risks and Controls

1. LLM provider rate limits may force fallback behavior.
- Control: clear runtime mode visibility and LLM usage analytics.

2. Registry data quality may vary.
- Control: manual review, notes, and override/update actions.

3. Operational drift between settings and behavior.
- Control: scheduler runtime health and configuration visibility.

## 8. Sign-off Note

This document captures the currently implemented and stabilized baseline as of freeze date and should be used as the business requirement reference for release validation.
