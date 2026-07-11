# SDK Management Platform — Enterprise Roadmap & Future Requirements

> **Vision:** A self-healing library governance platform that automatically discovers outdated dependencies across the entire Android and iOS portfolio, uses AI to generate context-aware upgrade recommendations with pros/cons, tracks upgrade ownership by squad, enforces SLA deadlines, generates compliance audit trails, and provides full cost visibility on AI usage — all with zero manual intervention after initial setup.
>
> Developers can chat with an AI about any library upgrade, get step-by-step migration guides, mark implementations complete (auto-updating the source of truth), and see the impact of their upgrades on the portfolio risk score in real time.

**Last Updated:** 2026-06-25  
**Document Version:** 2.0 (Comprehensive)

---

## 📌 Table of Contents

1. [Phase 1 — Executive & Management Features](#phase-1)
2. [Phase 2 — Technology Architecture Features](#phase-2)
3. [Phase 3 — Enterprise Governance](#phase-3)
4. [Phase 4 — AI-Powered Package Intelligence](#phase-4)
5. [Phase 5 — Developer Experience & Integrations](#phase-5)
6. [Phase 6 — Security & Access Control](#phase-6)
7. [Phase 7 — Data Quality & Operations](#phase-7)
8. [Phase 8 — Platform Expansion & Production Readiness](#phase-8)
9. [Missing DB Tables](#db-tables)
10. [Priority Matrix](#priority-matrix)
11. [Pitch Statement](#pitch)

---

## 🎯 Phase 1 — For Higher Management (C-Suite / VP Level) {#phase-1}

### 1. Executive Dashboard
- **Risk Score** — Single number (0–100): mandatory × 3 + deprecated × 2 + overdue × 5 + CVE count × 4
- **ROI Calculator** — "47 mandatory upgrades × 2 dev-days each = 94 dev-days at risk. AI saved ~120 hrs of research."
- **Compliance Health** — % libraries within SLA deadline, week-over-week trend sparkline
- **Cost of Inaction** — Libraries past deadline, estimated security exposure, CVE count
- **Upgrade Velocity** — Libraries upgraded this sprint vs last sprint
- **Trend indicators** — Is the portfolio getting better or worse over 30/60/90 days?

### 2. LLM Cost & Token Metrics
> DB table `llm_usage_log` already exists — needs API endpoints and UI

- Per pipeline run: total tokens (prompt + completion), estimated USD cost, cost per library
- Monthly/quarterly spend trend chart
- Rule-based vs LLM split (% using AI vs rule engine — cost comparison)
- Dashboard widget: "This month: 45,230 tokens | $2.18 | Saved ~40 hours manual work"
- Model-specific pricing table (GPT-4o: $5/1M, Claude: $3/1M, etc.) — configurable
- Cost per squad breakdown — "iOS team AI analysis cost $0.84 this month"
- Cost savings justification: hours × hourly rate vs LLM spend
- Budget alert: "You have used 80% of monthly LLM budget"

### 3. Executive PDF / Excel Report
- One-click "Export Board Report" — PDF with: portfolio overview, risk score, mandatory table, cost metrics
- Scheduled weekly email digest to leadership email list
- Per-squad breakdown section in report
- QR code linking to live dashboard in the PDF
- Compliance certificate page: "As of DATE, N% of libraries are within SLA"

### 4. Custom Dashboard Builder
- Drag-and-drop widgets: KPI tiles, charts, tables
- Save custom views per user role (CTO view, Dev Lead view, Developer view)
- Shareable dashboard URLs
- Embed mode for Confluence/SharePoint intranet pages

---

## 🔬 Phase 2 — For Technology Leaders / Architects {#phase-2}

### 5. AI Quality Metrics
- **Recommendation accuracy** — after upgrade completed, was AI decision correct? (thumbs up/down)
- **LLM vs Rule-based comparison** — side-by-side output comparison per library
- **Confidence scoring** — LLM returns 0–100% confidence with each recommendation
- **Feedback loop** — "Helpful / Not Helpful" per recommendation → feeds future prompt tuning
- **Drift detection** — LLM changing recommendations for same library without new version release

### 6. Pipeline Observability
- Step-level duration: scrape 2.3s | compare 0.1s | recommend 4.2s | notify 0.8s
- Success rate % per step, per registry type
- Cache hit rate (scrape cache TTL efficiency)
- Libraries failing scrape ≥3 times → auto-flagged for manual URL config
- Pipeline cost per run (tokens used × price)
- SLA: pipeline must complete within configurable timeout

### 7. Scraper Intelligence
- Registry coverage map — which libraries are auto-scraped vs manually tracked
- Per-registry API health dashboard (CocoaPods, Maven, GitHub rate limits)
- Scrape freshness heatmap — days since last successful scrape per library
- Rate limit visibility: "GitHub API: 4,200/5,000 requests remaining, resets in 2h"
- Retry queue: failed scrapes auto-retried with exponential backoff

### 8. Registry URL Configuration (Per-Library + Global)
> DB tables `scraper_registry_config` and `library_external_sources` already exist

**Global Registries (Settings page):**
- Maven Central / Private Artifactory / Nexus / GitHub Packages
- CocoaPods Trunk / Private Specs repo
- Swift Package Index / Custom SPM mirror
- GitHub API with personal access token (rate limit 5000/hr vs 60/hr unauthenticated)
- npm Registry (for future React Native support)

**Per-Library Override:**
- Custom scrape URL per library
- Auth headers per library (Bearer token, Basic auth)
- Custom parsing rule (JSON path, regex) for non-standard registries
- Test scrape button: "Scrape now and show result"

### 9. Multi-Model AI Comparison
- Run same library through GPT-4o AND Claude simultaneously
- Show side-by-side: did both models agree? If not, show both
- Trust score: 100% = both models agreed | 50% = disagreed
- Model fallback chain: "Try GPT-4o → if fails → Claude → if fails → rule-based"
- Cost comparison between models for same output quality

### 10. LLM Response Caching & Optimization
- Cache LLM response per (library_id, current_version, latest_version) — avoid duplicate calls
- Context window optimizer: smart truncation of release notes to fit model limits
- Hallucination guard: validate LLM output version numbers against scraped data
- Fine-tuning data collector: mark good LLM responses as training examples

### 11. RAG Knowledge Base
- Index all library changelogs, official docs URLs, CVE data as vector embeddings
- Chat queries retrieve relevant context from knowledge base before calling LLM
- Library-specific knowledge: your team's historical notes, custom comments
- Auto-index new releases when scraper detects a new version

---

## 🏗️ Phase 3 — For Enterprise Governance {#phase-3}

### 12. Full Audit Trail UI
> DB table `library_update_log` already has data — needs API endpoints and UI

- Who changed what, when, why — searchable and filterable table
- Example: "2026-06-20 | admin | retrofit | current_version: 2.9.0 → 2.11.0 | Reason: Q3 mandatory sprint"
- Filter by: user, date range, library, field changed, change type
- Export audit log to CSV/Excel for compliance team
- Immutable — records cannot be edited or deleted (append-only enforced)
- Audit report: "All changes in last 90 days" for SOC2/ISO27001 auditors

### 13. Upgrade Lifecycle Workflow
> DB table `upgrade_lifecycle` already exists — needs endpoints + UI

```
States per library:
  Pending → Acknowledged → Scheduled → In Progress → Completed / Skipped

Developer actions:
  Acknowledge:  "I've seen this. Taking ownership."
  Schedule:     Assign sprint + target date + developer name
  In Progress:  Mark as started, link feature branch
  Complete:     Enter actual new version + PR URL → auto-updates library record
  Skip:         Provide skip reason + next review date (stored in audit log)

Manager view:
  - Sprint 47: 12 libraries scheduled, 3 completed, 9 in progress, 2 overdue
  - Burndown chart per sprint
  - Cross-sprint backlog carry-over view
```

**Human-in-the-Loop — Implementation Tracking:**
1. AI recommends: "Upgrade Firebase 11.14 → 12.13"
2. Developer clicks "Mark as Implemented" in UI with PR URL
3. System automatically:
   - Updates `library.current_version` = new version
   - Updates `library.update_needed` = "none"
   - Writes `library_update_log` entry (who, when, from → to, reason)
   - Updates `upgrade_lifecycle.status` = "Completed"
   - Triggers re-scrape + re-compare + re-recommend for this library
   - Sends confirmation notification to team channel
4. Next pipeline run: current = latest → "Up to Date ✅"
5. Updates portfolio Risk Score automatically

### 14. Approval Workflow
- Some upgrades require sign-off before implementation (configurable by: platform, priority, library)
- Approval chain: Developer → Tech Lead → Architect → VP Engineering
- Email/Teams notification to approver with one-click approve/reject
- Approved upgrades unlock "Mark as Scheduled" button
- Rejection requires a comment (stored in audit log)
- Escalation if approval pending > N days

### 15. Team/Squad Ownership
> DB tables `library_ownership` and `application_teams` already exist — unused

- Assign libraries to squads (Android Team, iOS Team, Payments Team, Core Team)
- Per-squad dashboard: "iOS Team: 8 mandatory, 12 recommended, 0 overdue"
- Targeted notifications: "Android squad: you have 8 mandatory upgrades this quarter"
- Per-squad velocity leaderboard (gamification for motivation)
- Manager can see all squads' compliance status at a glance

### 16. SLA & Deadline Enforcement
- Configurable SLA rules: "Mandatory = 30 days | Recommended = 90 days | Optional = 180 days"
- Overdue escalation chain:
  - Day 7 overdue → notify developer
  - Day 14 overdue → notify team lead
  - Day 21 overdue → notify Engineering Manager
  - Day 30 overdue → notify VP Engineering / CTO
- Change freeze windows: block scheduling during App Store review weeks
- Calendar heatmap of upcoming deadlines
- SLA compliance % on executive dashboard

### 17. Policy Engine
- Define automated enforcement rules:
  - "No GPL-licensed libraries in commercial product"
  - "No libraries with CVSS security score > 7.0"
  - "No libraries more than 2 major versions behind latest"
  - "All mandatory upgrades must be acknowledged within 5 business days"
- Policy violations shown as alerts on dashboard
- Policy exceptions: request waiver with justification + expiry date
- Policy audit report: "N violations detected this month"

### 18. License Compliance
- Track license per library (MIT, Apache 2.0, GPL, LGPL, Commercial, Unknown)
- Flag GPL/AGPL libraries in commercial products (legal risk)
- License compatibility matrix (can Apache + MIT be used together?)
- SBOM (Software Bill of Materials) export — SPDX 2.3 and CycloneDX format
  - Required by: US Executive Order 14028, EU Cyber Resilience Act, many enterprise procurement teams
- License change alert: "Library X changed from MIT to BSL — action required"

---

## 🤖 Phase 4 — AI-Powered Package Intelligence {#phase-4}

### 19. LLM-Enhanced Pipeline (Release Notes Intelligence)
> DB field `scrape_cache.release_notes` already exists but is always empty

```
Enhanced pipeline:
  scrape → fetch_release_notes → LLM_analyze → compare → recommend_with_context

fetch_release_notes step:
  1. Detect repo URL from library.repo_url or library_external_sources
  2. Sources (in order of preference):
     a. GitHub API: GET /repos/{owner}/{repo}/releases
     b. CHANGELOG.md from repo root
     c. Official release page URL (configurable per library)
     d. CocoaPods changelog URL
  3. Cache in scrape_cache.release_notes (TTL: 24h)
  4. LLM receives: release notes + current version context

LLM generates per library:
  - Summary: 3–5 bullet points of what changed
  - Breaking changes list (API-level, with code examples)
  - Migration steps (numbered, with code snippets)
  - Security fixes (Y/N + CVE IDs if mentioned)
  - Effort estimate: Low (< 1hr) / Medium (1 day) / High (> 1 day)
  - Compatibility risk: which other libraries in stack may be affected
```

### 20. Package Profile Page (Detailed Report)
```
New UI page: /package/{library_id}  (linked from Libraries table)

┌──────────────────────────────────────────────────────────────┐
│  📦 Firebase iOS SDK  v11.14.0 → v12.13.0                    │
│  iOS | Mandatory | 🔴 High Priority | Squad: iOS Team        │
├──────────────────────────────────────────────────────────────┤
│  TABS:                                                        │
│  Overview | Release Notes | Migration | Security | Chat | Stats│
├──────────────────────────────────────────────────────────────┤
│  Overview:                                                    │
│  - Version timeline chart (all upgrades ever applied)        │
│  - Community health: GitHub stars, last commit date          │
│  - License: Apache 2.0 (compliant ✅)                        │
│  - CVE / Security status (OSV.dev API)                       │
│  - Maintainer activity score                                 │
│  - Download/usage statistics (from registry)                 │
│                                                              │
│  Release Notes (LLM-summarised):                             │
│  - v12.13.0: Added Vertex AI. Breaking: removed FIRApp       │
│  - v12.12.0: Performance +30% in Analytics module            │
│  - Full changelog diff: current version → latest             │
│                                                              │
│  Migration Guide (LLM-generated):                            │
│  Step 1: Update Podfile: pod 'Firebase/Core', '~> 12.13'     │
│  Step 2: Replace FIRApp.configure() with FirebaseApp.configure│
│  Step 3: Update Analytics calls: [FIRAnalytics] → Analytics  │
│  Estimated effort: 1–2 dev days                              │
│  Affected files: ~5 Swift files                              │
│                                                              │
│  Security Tab:                                               │
│  - CVE-2024-XXXX: CVSS 7.2 — Fixed in 12.11.0 ✅            │
│  - OSV.dev vulnerability scan result                         │
│  - Security score: 9/10                                      │
│                                                              │
│  Chat Tab:                                                   │
│  "Ask anything about this library"                           │
│  [Type your question here...]                                │
│  Context injected automatically:                             │
│    - Current vs latest version                               │
│    - Full release notes                                      │
│    - Your team's historical notes                            │
│    - Known CVEs                                              │
│  Chat history saved per library per user                     │
│                                                              │
│  Stats Tab:                                                  │
│  - Updated 3× in this app (2024-01, 2025-03, 2026-06)       │
│  - Avg upgrade lag: 45 days                                  │
│  - Time-to-upgrade trend chart                               │
│  - LLM tokens spent on this library: 4,200 tokens / $0.021   │
│  - Recommendation history                                    │
└──────────────────────────────────────────────────────────────┘
```

### 21. Natural Language Search & AI Commands
- "Show me all iOS libraries that are deprecated with no replacement"
- "Which Firebase libraries can be upgraded together in one PR?"
- "What's our most expensive library to maintain?"
- "Show libraries overdue for >30 days owned by iOS team"
- "Which upgrades have security fixes I haven't applied yet?"
- Powered by LLM with DB query generation (Text-to-SQL)

### 22. Predictive Analytics
- "At current velocity, you'll have 23 critical overdue upgrades by Q4"
- Version drift score: portfolio average days behind latest
- Upgrade effort forecast: AI estimates total dev-hours needed for backlog
- "If you upgrade these 5 Firebase libraries now, Risk Score drops from 72 → 45"

### 23. CVE / Security Intelligence
- Integrate with OSV.dev (free, no API key): `https://api.osv.dev/v1/query`
- Per-library vulnerability scan on each pipeline run
- CVSS severity scores displayed in Libraries table
- Auto-escalate libraries with CVSS > 7.0 to "Critical" alert_priority
- Security digest: weekly email listing new CVEs in your portfolio
- CVE badge on library card: 🔴 Known CVE | ✅ Clean | ❓ Unknown

---

## 👨‍💻 Phase 5 — Developer Experience & Integrations {#phase-5}

### 24. Import from Project Files
- **Gradle import**: Parse `build.gradle` / `libs.versions.toml` — auto-populate Android libraries
- **Podfile import**: Parse `Podfile` and `Podfile.lock` — auto-populate iOS libraries
- **Package.swift import**: SPM manifest parsing
- **Excel/CSV import**: Upload existing spreadsheet-tracked libraries (bulk_import_job table exists)
- **GitHub repo scan**: Provide org URL → auto-discover all dependency files across all repos

### 25. Bulk Operations
- Select multiple libraries → bulk: acknowledge / schedule / assign to squad / change priority
- Bulk import with validation: show errors per row, fix inline, re-import
- Bulk export: filtered view to CSV/Excel
- "Select all mandatory upgrades → assign to iOS team → schedule Sprint 47"

### 26. CI/CD Integration
- **GitHub Actions workflow**: Run `lib-manager check` in PR pipeline
  - Fails if new mandatory upgrade is introduced
  - Posts comment: "⚠️ This PR adds Firebase 11.x (mandatory upgrade available: 12.13)"
- **Jenkins plugin**: Same check for Jenkins pipelines
- **Pre-commit hook**: Warn developer before committing with outdated dependency
- **Webhook outbound**: POST to custom URL when new upgrade detected (trigger custom workflows)

### 27. REST API for External Integrations
- Full public REST API with OpenAPI/Swagger docs (currently debug-mode only)
- API key management: generate keys per team/application
- Rate limiting per API key
- Webhooks: subscribe to events (new_version_detected, mandatory_upgrade_detected, etc.)
- GraphQL endpoint (future) for flexible querying

### 28. Notification Enhancements
- **In-app notification bell** — badge count on sidebar, click to view history
- **Notification preferences per user** — each user configures frequency, channels, thresholds
- **Digest mode**: one weekly summary vs immediate per-event alerts
- **WhatsApp / SMS**: additional channels via Twilio or AWS SNS
- **Customizable templates**: edit email/Teams message HTML/Markdown per notification type
- **Escalation rules**: define multi-level chains with configurable delays
- **Do Not Disturb**: quiet hours, vacation mode (notifications held, delivered on return)
- **Read receipts**: track who has seen a notification

### 29. Developer Self-Service Tools
- **Slack bot**: `/lib-status retrofit` → current version, recommendation, next deadline
- **GitHub Actions comment bot**: auto-comment on PRs that touch dependency files
- **VS Code extension**: hover over Gradle/Podfile → popup shows upgrade status + AI recommendation
- **CLI tool**: `lib-manager status --platform android` for terminal/script users
- **Browser extension**: show upgrade status on Maven Central / CocoaPods / NPM package pages

---

## 🔐 Phase 6 — Security & Access Control {#phase-6}

### 30. Expanded RBAC (Role-Based Access Control)
> Current: admin | viewer — insufficient for enterprise

```
New roles:
  super_admin   — manage users, roles, system config, all libraries
  admin         — manage libraries, approve workflows, view everything
  tech_lead     — approve upgrades for their squad, edit lifecycle
  developer     — mark upgrades in progress/complete, view and chat
  viewer        — read-only: libraries, recommendations, dashboard
  external      — read-only: limited to specific libraries/squads
  api_service   — non-human: CI/CD pipeline access only
```

### 31. User Management UI
- Create / edit / deactivate users without DB access
- Assign users to squads/teams
- View active sessions per user
- Force logout (revoke all tokens for a user)
- Password reset by admin (send reset link via email)

### 32. Password & Session Management
- Users can change their own password from profile page
- Password complexity rules (configurable)
- JWT token expiry configuration (currently hardcoded)
- Session list: "Logged in from Chrome macOS on 2026-06-25"
- Inactive session timeout
- Remember me / stay logged in option

### 33. SSO / SAML Integration
- Azure Active Directory (Entra ID) integration
- Okta SAML 2.0 support
- Google Workspace SSO
- Auto-provision user accounts from corporate directory
- Group sync: Azure AD groups → app roles automatically

### 34. API Security
- API key management UI (generate, rotate, revoke per integration)
- IP allowlist: restrict API/UI access to corporate network ranges
- Audit log of all API key usage
- LLM API key rotation workflow: update key, test, confirm — no downtime

### 35. Data Protection
- Field-level encryption for sensitive config (LLM API keys, SMTP passwords, webhook URLs)
- Mask sensitive values in audit logs and UI
- Data masking for external viewers: hide API keys, credentials
- Secret scanning: alert if potential API keys appear in library comments/notes

---

## 🗃️ Phase 7 — Data Quality & Operations {#phase-7}

### 36. Data Import & Validation
- Import libraries from CSV/Excel with column mapping UI
- Row-level validation: show errors inline ("version must be semver", "platform must be Android/iOS")
- Duplicate detection: flag when same library tracked twice with different package names
- Data completeness score per library: "6/10 fields populated"

### 37. Data Quality Rules
- Validation rules engine: "package name must contain : for Maven", "iOS libraries must have cocoapods or spm registry"
- Auto-correction suggestions: "Did you mean com.squareup.retrofit2:retrofit?"
- Quality dashboard: % libraries with complete data vs stubs

### 38. Archive & Restore
- Soft delete libraries (archive, not permanent delete)
- Archived libraries excluded from pipeline runs and dashboard counts
- Restore archived library with full history intact
- Permanent delete (super_admin only, with confirmation + audit log entry)

### 39. Data Retention Policy Execution
> DB table `app_settings` has retention config — needs execution engine

- Auto-purge pipeline run details older than N days (configurable, default 180)
- Auto-purge notification log older than N days (default 365)
- Auto-purge scrape cache expired entries (daily cleanup job)
- Auto-purge LLM usage log older than N days (default 365)
- Retention policy dashboard: "Next cleanup in 3 days | Will free ~45MB"

### 40. Database Backup & Restore UI
- Trigger manual database backup from Settings page
- View backup history with size and timestamp
- Download backup file
- Restore from backup with confirmation
- Scheduled backups: daily at configurable time (db_backup_keep_count in app_settings)

### 41. Operational Tools in UI
- **Service health + restart**: Admin can restart individual services from Settings without terminal
- **Log viewer**: View recent service logs from UI (last 500 lines per service)
- **Scrape cache management**: View all cache entries, see expiry, manually invalidate per library
- **Database stats**: table sizes, record counts, last vacuum date
- **Rate limit dashboard**: current API rate limit status for GitHub, Maven, CocoaPods

### 42. Dependency Deduplication & Merge
- Detect when the same library appears under two different package names
- Merge two library records: combine history, recommendations, lifecycle records
- Split one library into two (when a library gets forked/renamed)
- Track library renames: "android.support → androidx (migration detected)"

---

## 🌐 Phase 8 — Platform Expansion & Production Readiness {#phase-8}

### 43. Multi-App / Multi-Environment Support
- Track libraries across multiple applications (App1, App2, Shared SDK)
- Per-app dashboard: "App1 risk: 72 | App2 risk: 34 | Shared SDK risk: 58"
- Shared library tracking: same dependency in multiple apps — upgrade once shown as "fixes all"
- Environment tracking: what version is in Dev / Staging / Production per app?
- Cross-app impact: "Upgrading this library affects 3 out of 4 apps"

### 44. Platform / Ecosystem Expansion
- **React Native**: npm registry support (`package.json` import)
- **Flutter**: pub.dev registry support (`pubspec.yaml` import)
- **Web Frontend**: npm / yarn (`package.json`)
- **Backend Java/Kotlin**: Maven POM files
- **Python**: PyPI (`requirements.txt`, `pyproject.toml`)
- **Go modules**: `go.mod` support
- Platform filter in all pages remains consistent

### 45. Production Infrastructure
- **PostgreSQL migration**: Switch from SQLite to PostgreSQL for multi-instance production
- **Alembic migrations**: Proper schema versioning (alembic_version table exists but unused)
- **Docker Compose**: Full stack deployment with one command
- **Kubernetes manifests**: Production-grade deployment with health probes, resource limits
- **Terraform modules**: Cloud infrastructure as code (AWS / Azure / GCP)
- **Secret management**: HashiCorp Vault / Azure Key Vault integration (replace .env files)
- **Load balancing**: Multiple ui-service instances behind nginx

### 46. Observability & Monitoring
- **Prometheus metrics endpoint**: `/metrics` on each service (request count, latency, errors)
- **Grafana dashboard**: Real-time service health, pipeline performance, LLM costs
- **OpenTelemetry tracing**: Distributed trace per pipeline run (scrape → compare → recommend)
- **Alert manager**: PagerDuty / OpsGenie integration for service down alerts
- **Health check page improvement**: Show service uptime %, response time charts

### 47. BI Tool Integration
- **Power BI connector**: DirectQuery from Azure or REST connector
- **Tableau**: Data extract API endpoint returning standardised JSON
- **Grafana**: Already covered via Prometheus + Grafana
- **CSV/XLSX scheduled export**: Auto-email data dumps to BI team

### 48. CI/CD Pipeline (App itself)
- **GitHub Actions workflows**: test → lint → docker build → deploy on merge
- **Automated tests**: pytest with coverage report in CI
- **Pre-commit hooks**: black, ruff, mypy for code quality
- **Dependabot**: Keep the lib-management app's own dependencies updated (meta!)
- **Blue/Green deployment**: Zero-downtime upgrades of the platform itself

---

## 🎨 Phase 9 — User Experience Polish {#phase-9}

### 49. Global Search
- Search across all pages: libraries, recommendations, audit log, pipeline runs
- Search bar in navigation: type any library name, package, or SDK name
- Keyboard shortcut: Cmd+K / Ctrl+K to open search
- Search history per user
- Fuzzy search: "firebas" matches "Firebase"

### 50. In-App Notifications Bell
- Bell icon in sidebar with unread badge count
- Click to see notification feed: "New mandatory upgrade: Firebase 12.14.0 detected"
- Mark as read / mark all as read
- Notification preferences link from bell
- Browser push notifications (web notification API)

### 51. User Profile & Preferences
- Profile page: display name, email, avatar, squad, timezone
- Personal preferences: dark mode, default platform filter, notification settings
- Activity feed: "Your recent changes in the last 30 days"
- Password change from profile

### 52. UX Improvements
- **Dark mode**: Toggle in user preferences (Streamlit supports custom CSS theming)
- **Keyboard shortcuts**: J/K to navigate library list, E to expand, Esc to close
- **Loading skeletons**: Placeholder shimmer instead of blank while loading
- **Undo**: 5-second undo window after delete operations
- **Breadcrumb navigation**: Home > Libraries > Firebase iOS SDK
- **Bulk selection**: Checkbox per row in tables for bulk operations
- **Sticky table headers**: Headers remain visible when scrolling long tables

### 53. Accessibility (WCAG 2.1 AA)
- Screen reader compatible (proper ARIA labels)
- Keyboard navigable (tab order, focus indicators)
- Colour contrast minimum 4.5:1
- Status not indicated by colour alone (always include icon/text)
- Form labels always visible (not placeholder-only)

### 54. Internationalization
- English primary (current)
- Language selector: Japanese, German, French for future enterprise customers
- Date/time format respects user timezone setting
- Number formatting (1,234 vs 1.234 depending on locale)

---

## 🗄️ New DB Tables Required {#db-tables}

| Table | Purpose | Status | Priority |
|-------|---------|--------|----------|
| `library_chat_history` | Per-library AI chat messages + history per user | 🔴 New | P2 |
| `llm_feedback` | Developer "helpful / not helpful" ratings | 🔴 New | P2 |
| `package_release_notes` | Cached LLM-summarised release notes per version | 🔴 New | P2 |
| `registry_auth_config` | Per-registry tokens, headers, base URLs | 🔴 New | P1 |
| `sla_rules` | Configurable SLA per update_needed type | 🔴 New | P1 |
| `approval_requests` | Pending/approved/rejected upgrade approvals | 🔴 New | P2 |
| `policy_rules` | Policy engine rules (no GPL, no CVSS>7) | 🔴 New | P2 |
| `cve_scan_results` | OSV.dev scan results per library per pipeline run | 🔴 New | P2 |
| `library_license` | License type per library (MIT, Apache, GPL) | 🔴 New | P2 |
| `user_sessions` | Active JWT sessions per user | 🔴 New | P1 |
| `user_preferences` | Per-user notification prefs, dark mode, filters | 🔴 New | P2 |
| `api_keys` | External API keys for integrations | 🔴 New | P2 |
| `in_app_notifications` | Bell icon notification feed per user | 🔴 New | P2 |
| `multi_app_registry` | Multiple applications tracked | 🔴 New | P3 |
| `environment_versions` | Per-app, per-env current version tracking | 🔴 New | P3 |
| `sbom_exports` | Generated SBOM snapshot per date | 🔴 New | P3 |
| `upgrade_lifecycle` | Sprint/completion workflow | 🟡 Exists, unused | P1 |
| `library_ownership` | Squad assignments per library | 🟡 Exists, unused | P1 |
| `application_teams` | Squad/team definitions | 🟡 Exists, unused | P1 |
| `llm_usage_log` | Token and cost tracking | 🟡 Exists, UI missing | P1 |
| `library_update_log` | Audit trail (all field changes) | 🟡 Exists, UI missing | P1 |
| `scraper_registry_config` | Registry URL configs | 🟡 Exists, unused | P1 |
| `library_external_sources` | Per-library changelog/docs URLs | 🟡 Exists, unused | P1 |
| `bulk_import_job` | Import job tracking | 🟡 Exists, unused | P2 |
| `llm_prompt_templates` | Custom prompts (DB-driven) | 🟢 Exists, connected | Done |
| `llm_config` | LLM provider config | 🟢 Exists, UI built | Done |
| `app_settings` | Application configuration KV store | 🟢 Exists, UI built | Done |

---

## 📊 Complete Priority Matrix {#priority-matrix}

### 🔴 P1 — Build Now (Max ROI, Low Effort)

| Feature | Effort | Impact | Notes |
|---------|--------|--------|-------|
| LLM cost metrics page (`llm_usage_log`) | S | CFO / CTO visibility | Table exists |
| Audit Trail UI (`library_update_log`) | S | Compliance / SOC2 | Table has data |
| Risk Score dashboard widget | S | One number for execs | Pure calculation |
| Upgrade Lifecycle workflow UI | M | Management KPI / SLA | Table exists |
| Human-in-the-loop implementation tracking | M | Closes feedback loop | Needs UI |
| Registry URL config per library | S | Private/internal repos | Table exists |
| User Management page (create/edit users) | S | Security / enterprise | Missing entirely |
| Password change for users | S | Basic security | Missing entirely |

### 🟡 P2 — Next Quarter (High Value, Medium Effort)

| Feature | Effort | Impact | Notes |
|---------|--------|--------|-------|
| Squad/team ownership UI | M | Enterprise org structure | Tables exist |
| SLA enforcement + escalation engine | M | Compliance deadline | Needs scheduler |
| CVE / OSV.dev security integration | M | Security compliance | Free public API |
| Release notes fetch + LLM summarise | M | Developer productivity | scrape_cache ready |
| Package Profile page (detailed report) | L | Developer experience | New page |
| Per-library Chat interface | L | AI differentiator | New table needed |
| Executive PDF report export | M | Board meetings | Needs lib |
| In-app notification bell | M | UX completeness | New table needed |
| Approval workflow | M | Enterprise governance | New table needed |
| License compliance + SBOM | M | Legal / procurement | OSV.dev API |
| Bulk operations (multi-select) | S | Power user efficiency | UI only |
| Data import from Gradle/Podfile | M | Auto-discovery | Parser needed |

### 🟢 P3 — Future (Strategic, Higher Effort)

| Feature | Effort | Impact | Notes |
|---------|--------|--------|-------|
| Policy engine (rules enforcement) | L | Enterprise governance | New engine |
| Multi-app / multi-environment | L | Portfolio management | Schema change |
| Platform expansion (npm, PyPI, Flutter) | L | Broader adoption | New scrapers |
| SSO / SAML / Azure AD integration | L | Enterprise security | Auth overhaul |
| Natural language search (Text-to-SQL) | L | AI UX differentiator | LLM-powered |
| Predictive analytics | L | Forward planning | ML models |
| GitHub Actions integration | M | CI/CD workflow | API needed |
| Slack bot | L | Developer adoption | Slack API |
| VS Code extension | XL | Developer experience | Extension dev |
| PostgreSQL migration | L | Production readiness | Schema migration |
| Docker / Kubernetes deployment | M | DevOps | IaC files |
| Prometheus + Grafana monitoring | M | Observability | Metrics endpoint |
| Power BI / Tableau connector | M | Analytics integration | Data API |
| Fine-tuning data collection + RAG | XL | AI quality | ML pipeline |
| WCAG 2.1 accessibility | M | Enterprise procurement | CSS/ARIA |

---

## 💡 The "Wow Factor" Pitch {#pitch}

### For the CTO
> *"This platform gives us a single pane of glass across all 119 mobile libraries. It auto-detects every new release, uses AI to generate migration guides, tracks who is upgrading what by sprint, enforces SLA deadlines with escalation, and generates SBOM exports for compliance — with full audit trail. Our Risk Score dropped from 87 to 42 this quarter."*

### For the CFO
> *"AI analysis costs ~$2 per month total. We eliminated approximately 40 hours of manual spreadsheet tracking and changelog reading. That's 40 × $80/hr = $3,200 saved per month from a $2 spend."*

### For the Developer
> *"I open one page, see exactly what I need to upgrade, click to get the AI migration guide, ask it 'what breaks in my Swift files', mark it done — and the system updates everything automatically. No Jira tickets, no spreadsheets."*

### For the CISO / Security Team
> *"Every library is scanned against OSV.dev on every pipeline run. CVE alerts are automatic. SBOM exports are one click. Every change is immutably audited. License compliance rules are enforced automatically."*

### The One-Line Summary
> *"GitHub Dependabot for enterprise mobile — with AI-powered migration guides, squad-level governance, SLA enforcement, cost tracking, and a conversational interface that answers 'how do I upgrade this?' in plain English."*

---

*Document Version: 2.0*  
*Created: 2026-06-25*  
*Last Updated: 2026-06-25*  
*Next Review: Quarterly*  
*Owner: Platform Engineering*
