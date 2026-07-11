# Library Management Application — Enterprise Architecture & Development Plan

**Document Version:** 2.4  
**Date:** June 25, 2026  
**Architecture Level:** Enterprise / Production-Grade  
**Tech Approach:** Microservices · Python 3.12 · Streamlit UI · LLM-Assisted Recommendations · Docker · SQLite · Design Patterns · Persona-Based Access · UI-Configurable Everything · Multi-Framework Extensible Architecture  
**Current Scope:** Android (Maven) + iOS (CocoaPods/SPM) — MVP  
**Future Scope:** npm · PyPI · NuGet · Gradle Plugins · Pub/Flutter · Any-Framework  
**Status:** FOR REVIEW — Development has not started

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Microservice Catalog](#2-microservice-catalog)
3. [Technology Stack](#3-technology-stack)
4. [Design Patterns Applied](#4-design-patterns-applied)
5. [Folder & File Structure](#5-folder--file-structure)
6. [Database Design](#6-database-design)
7. [API Contracts](#7-api-contracts)
8. [Inter-Service Communication](#8-inter-service-communication)
9. [Security Design](#9-security-design)
10. [Docker & Container Strategy](#10-docker--container-strategy)
11. [Error Handling & Resilience](#11-error-handling--resilience)
12. [Logging & Observability](#12-logging--observability)
13. [Testing Strategy](#13-testing-strategy)
14. [Development Phases](#14-development-phases)
15. [Code Quality & Optimization](#15-code-quality--optimization)
16. [Streamlit UI — Dashboard & Management](#16-streamlit-ui--dashboard--management)
    - 16.1 Technology Choice
    - 16.2 Login · 16.3 Dashboard · 16.4 Library Detail
    - 16.5 Management · 16.6 Scheduler Config · 16.7 Notifications Config
    - 16.8 **LLM Configuration** · 16.9 **Scraper Configuration**
    - 16.10 **System Health** · 16.11 User Management
17. [Persona-Based Access Control](#17-persona-based-access-control)
18. [Multi-Framework Extensibility Roadmap](#18-multi-framework-extensibility-roadmap)
19. [Business Gaps & Enhancements](#19-business-gaps--enhancements)
20. [Technical Gaps & Hardening](#20-technical-gaps--hardening)

---

## 1. Architecture Overview

### 1.1 System Design

The Library Management Application is built as a **Python 3.12 microservices system**, containerized with Docker. Each service owns a single responsibility, communicates over HTTP REST, and shares no runtime state. The scheduler orchestrates the full pipeline on a configurable cron schedule.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            CLIENT / USERS                                │
│          Admin Browser · Viewer Browser · Email · Microsoft Teams        │
└────────────────┬─────────────────────────────────┬────────────────────── ┘
                 │ HTTP :8501                       │ HTTP :8000
┌────────────────▼─────────────────┐  ┌────────────▼──────────────────────┐
│     STREAMLIT UI  :8501          │  │      API GATEWAY  :8000           │
│  Dashboard · Management · Admin  │  │  JWT Auth · Rate Limit · Routing  │
│  Persona Login (Admin / Viewer)  │  └──┬──────────┬──────────┬───────┬──┘
└────────────────┬─────────────────┘     │          │          │       │
                 │ REST calls via        ▼          ▼          ▼       ▼
                 │ API Gateway        :8001       :8002      :8003   :8004
                 └───────────────►  Library    Scraper   Comparison Recom-
                                    Data       Service    Service   mendation
                                    Service                         Service
                                      │
                                    :8005      :8006
                                  Notif-     Scheduler
                                  ication    Service
                                  Service    APScheduler
                                      │          │
                              ┌───────┴──────────┘
                              ▼
                    ┌─────────────────────┐
                    │   SQLite Database   │
                    │ library_management  │
                    │       .db           │
                    └─────────────────────┘
```

### 1.2 Pipeline Flow (scheduled run)

### 1.3 Current Scope vs. Future Framework Coverage

The application is designed with a **plugin-based extensibility architecture** from day one. The scraper Strategy pattern and registry configuration table mean that adding support for a new package ecosystem requires **only a new strategy file + one line in the factory** — no changes to any other service.

| Release | Ecosystem | Language / Framework | Registry | Status |
|---------|-----------|---------------------|----------|--------|
| **MVP (v1)** | Mobile — Android | Kotlin / Java | Maven Central | ✓ **Build now** |
| **MVP (v1)** | Mobile — iOS | Swift / ObjC | CocoaPods + SPM | ✓ **Build now** |
| **MVP (v1)** | Vendored / Binary | Any | GitHub Releases + Custom HTTP | ✓ **Build now** |
| v2 | Web / Node.js | JavaScript / TypeScript | npm registry | Planned |
| v2 | Backend / Scripts | Python | PyPI | Planned |
| v3 | Backend / Enterprise | C# / .NET | NuGet Gallery | Planned |
| v3 | Mobile | Dart / Flutter | pub.dev | Planned |
| v4 | Build tooling | Groovy / Kotlin DSL | Gradle Plugin Portal | Planned |
| v4 | Backend / Systems | Java | Maven Central (already supported) | Planned |
| v5+ | Backend / Systems | Go | Go Module Proxy | Future |
| v5+ | Backend / Systems | Rust | Crates.io | Future |
| v5+ | Backend / Desktop | Ruby | RubyGems | Future |
| Any | Custom / Internal | Any | Admin-configured URL | ✓ **Build now** |

> **Design principle:** The business logic (comparison, recommendation, notification) is **100% registry-agnostic**. Only the scraper-service knows about registries. Adding a new ecosystem does not touch comparison, recommendation, notification, scheduler, or UI services.

---

### 1.4 Pipeline Flow (scheduled run)

```
Scheduler triggers
      │
      ▼
[1] Library Data Service   → reads 119 libraries from SQLite (current versions)
      │
      ▼
[2] Scraper Service        → fetches latest version + release notes per library
      │                       (Maven, CocoaPods/SPM registries)
      ▼
[3] Comparison Service     → aggregates DB data + scraped data
                           → compares versions (semver)
                           → detects new releases
      │
      ▼
[4] Recommendation Service → upgrade vs. sufficient assessment
                           → generates pros/cons for both paths
                           → writes recommendations to DB
      │
      ▼
[5] Notification Service   → formats content for email + Teams
                           → sends on configured schedule
                           → logs delivery status
```

---

## 2. Microservice Catalog

### 2.1 Library Data Service (`library-data-service`)

| Property | Value |
|----------|-------|
| Port | 8001 |
| Responsibility | CRUD operations on the `libraries` and `version_history` tables |
| Pattern | Repository Pattern + Unit of Work |
| DB access | Only service with direct SQLite write access (for library metadata) |
| Language | Python 3.12 + FastAPI + SQLAlchemy |

**Endpoints summary:**
- `GET /libraries` — list all libraries with filters (platform, status, update_needed)
- `GET /libraries/{id}` — get single library
- `PUT /libraries/{id}` — update library record
- `GET /libraries/platform/{platform}` — filter by Android/iOS
- `GET /version-history/{library_id}` — get version history
- `POST /version-history` — record new version entry
- `GET /health` — health check

---

### 2.2 Scraper Service (`scraper-service`)

| Property | Value |
|----------|-------|
| Port | 8002 |
| Responsibility | Fetch latest library version + release notes from any registered package registry |
| Pattern | Strategy Pattern (one strategy per registry) + Circuit Breaker + Plugin Registry |
| External calls | Maven Central · CocoaPods API · Swift Package Index · GitHub Releases · npm · PyPI · NuGet · pub.dev · Custom HTTP |
| Language | Python 3.12 + FastAPI + HTTPX (async) + tenacity (retry) |

**How to add a new registry (extensibility pattern):**
```
1. Create  strategies/npm.py  →  class NpmScraper(ScraperStrategy)
2. Add one line to factory.py:  RegistryType.NPM: NpmScraper()
3. Add row to  scraper_registry_config  DB table (via UI or migration)
4. No changes to any other service needed
```

**Registry strategies — MVP (v1) + Planned:**

| Registry | Ecosystem | Phase | Endpoint | Status |
|----------|-----------|-------|----------|--------|
| Maven Central | Android / Java | MVP | `search.maven.org/solrsearch/select` | ✓ Build now |
| CocoaPods Trunk | iOS pods | MVP | `trunk.cocoapods.org/api/v1/pods/{name}` | ✓ Build now |
| Swift Package Index | iOS SPM | MVP | `swiftpackageindex.com/api/packages` | ✓ Build now |
| GitHub Releases API | Vendored/binary SDKs | MVP | `api.github.com/repos/{owner}/{repo}/releases/latest` | ✓ Build now |
| Custom HTTP | ACI/IPWorks/Scandit/Gigya | MVP | Admin-configured URL per library | ✓ Build now |
| npm registry | JavaScript / TypeScript | v2 | `registry.npmjs.org/{package}` | Planned |
| PyPI | Python | v2 | `pypi.org/pypi/{package}/json` | Planned |
| NuGet Gallery | C# / .NET | v3 | `api.nuget.org/v3/registration5/{id}/index.json` | Planned |
| pub.dev | Dart / Flutter | v3 | `pub.dev/api/packages/{name}` | Planned |
| Gradle Plugin Portal | Gradle plugins | v4 | `plugins.gradle.org/api/search` | Future |
| Go Module Proxy | Go | v5 | `proxy.golang.org/{module}/@latest` | Future |
| Crates.io | Rust | v5 | `crates.io/api/v1/crates/{name}` | Future |
| RubyGems | Ruby | v5 | `rubygems.org/api/v1/gems/{name}.json` | Future |

**Endpoints summary:**
- `POST /scrape` — scrape one library `{package, registry}`
- `POST /scrape/batch` — scrape list of libraries
- `GET /scrape/status/{job_id}` — async job status
- `GET /registries` — list supported registries
- `GET /health`

---

### 2.3 Comparison Service (`comparison-service`)

| Property | Value |
|----------|-------|
| Port | 8003 |
| Responsibility | Aggregate DB + scraped data, compare versions, detect new releases |
| Pattern | Service Layer + DTO (Data Transfer Objects) |
| Input | Library Data Service + Scraper Service results |
| Output | `version_comparison_result` records written to DB |
| Language | Python 3.12 + FastAPI + packaging (semver comparison) |

**Version comparison logic:**
```
current_version (DB)  vs  latest_version (scraped)
      │
      ├── packaging.version.parse() for semver comparison
      ├── If latest > current  →  new_version_released = True
      ├── If latest == current →  new_version_released = False
      └── If unparseable       →  flag for manual review
```

**Endpoints summary:**
- `POST /compare` — compare single library
- `POST /compare/batch` — compare all libraries
- `GET /comparisons` — list all comparison results
- `GET /comparisons/{library_id}` — latest result for a library
- `GET /health`

---

### 2.4 Recommendation Service (`recommendation-service`)

| Property | Value |
|----------|-------|
| Port | 8004 |
| Responsibility | Generate upgrade guidance, pros/cons for each library using LLM or rule-based fallback |
| Pattern | Strategy Pattern (LLM-assisted vs. rule-based) + Template Method + Factory |
| Input | Comparison results + release notes + deprecation notes + LLM config from DB |
| Output | `recommendations` table rows |
| Language | Python 3.12 + FastAPI + Jinja2 + openai/anthropic SDK |

**LLM Integration Flow:**
```
Recommendation Request
      │
      ▼
Load LLM config from DB (provider, model, API key, prompts)
      │
      ├── LLM enabled?  YES → LLMRecommendationGenerator
      │                         └─ Build prompt from llm_prompt_templates
      │                         └─ Call LLM API (OpenAI / Azure / Ollama)
      │                         └─ Parse response → pros[], cons[], summary
      │
      └── LLM enabled?  NO  → Rule-based fallback generators
```

**LLM Prompt structure (per recommendation type):**
```
System prompt:  "You are a software library upgrade advisor..."
User prompt:    "Library: {package} | Platform: {platform}
                 Current version: {current} | Latest version: {latest}
                 Release notes: {release_notes}
                 Deprecation notes: {deprecation_notes}
                 Update priority: {update_needed}
                 Generate: upgrade_pros, upgrade_cons, no_upgrade_pros,
                           no_upgrade_cons, recommendation_summary
                 Format: JSON"
```

**Recommendation logic per library:**
```
IF status == 'Deprecated'
    → upgrade_recommended = 'Yes' (forced migration)
    → LLM generates: pros/cons based on deprecation notes

ELIF new_version_released AND update_needed == 'Mandatory'
    → upgrade_recommended = 'Yes'
    → LLM generates: pros/cons from release notes

ELIF new_version_released AND update_needed == 'Recommended'
    → upgrade_recommended = 'Yes' (advisable)
    → LLM generates: pros/cons from release notes

ELIF current == latest (in sync)
    → upgrade_recommended = 'Sufficient'
    → Rule-based: stability pros/cons (no LLM needed)

ELIF update_needed == 'None'
    → upgrade_recommended = 'No'
```

**Endpoints summary:**
- `POST /recommendations/generate/{library_id}` — generate for one library
- `POST /recommendations/generate/batch` — generate for all
- `GET /recommendations` — list all
- `GET /recommendations/{library_id}` — get for library
- `POST /recommendations/test-llm` — test LLM connection with sample payload
- `GET /health`

---

### 2.5 Notification Service (`notification-service`)

| Property | Value |
|----------|-------|
| Port | 8005 |
| Responsibility | Send email + Teams notifications with recommendation content |
| Pattern | Template Method Pattern (email vs. Teams formatter) + Observer |
| Channels | SMTP (email) · Microsoft Teams Incoming Webhook |
| Language | Python 3.12 + FastAPI + aiosmtplib + httpx + Jinja2 |

**Email template sections:**
- Summary table (library · current → latest · status · recommendation)
- Mandatory upgrades section
- Deprecated libraries section
- Recommended upgrades section
- Critical alerts (cert expiry, security patches)

**Teams card template:**
- Adaptive Card format
- Color-coded by urgency (red=Mandatory/Deprecated, yellow=Recommended, green=Sufficient)

**Endpoints summary:**
- `POST /notify/email` — send email notification
- `POST /notify/teams` — post Teams message
- `POST /notify/both` — send both channels
- `GET /notifications` — list notification log
- `GET /health`

---

### 2.6 Scheduler Service (`scheduler-service`)

| Property | Value |
|----------|-------|
| Port | 8006 |
| Responsibility | Orchestrate the full pipeline on a configurable schedule |
| Pattern | Chain of Responsibility (pipeline steps) |
| Scheduler | APScheduler 3.x with SQLite job store |
| Language | Python 3.12 + FastAPI + APScheduler |

**Pipeline steps (in order):**
1. Fetch libraries from Library Data Service
2. Batch scrape via Scraper Service
3. Batch compare via Comparison Service
4. Batch generate recommendations via Recommendation Service
5. Send notifications via Notification Service
6. Log pipeline run result

**Endpoints summary:**
- `GET /schedule` — view current schedule config
- `PUT /schedule` — update schedule (cron expression)
- `POST /run/now` — trigger manual pipeline run
- `GET /runs` — list pipeline run history
- `GET /health`

---

### 2.7 API Gateway (`api-gateway`)

| Property | Value |
|----------|-------|
| Port | 8000 |
| Responsibility | Single entry point, JWT auth, rate limiting, routing |
| Pattern | Facade Pattern |
| Language | Python 3.12 + FastAPI + python-jose (JWT) + slowapi (rate limit) |

---

### 2.8 UI Service (`ui-service`) — Streamlit Dashboard

| Property | Value |
|----------|-------|
| Port | 8501 |
| Responsibility | Web-based dashboard for library management, monitoring, and configuration |
| Pattern | MVC-lite (pages as controllers, API Gateway as model, Streamlit as view) |
| Auth | Persona-based login (Admin / Viewer) — session state + JWT issued via API Gateway |
| Language | Python 3.12 + Streamlit 1.35.x |
| Data source | All data fetched from API Gateway (:8000) — never directly from DB |

**Pages & Access:**

| Page | Admin | Viewer | Description |
|------|-------|--------|-------------|
| Login | ✓ | ✓ | Username + password → role assigned |
| Dashboard | ✓ | ✓ | Summary metrics + full library table with filters |
| Library Detail | ✓ | ✓ | All fields, version history, recommendation, last-updated reason |
| Management | ✓ | ✗ | Edit library info, add external URL, set update reason |
| Scheduler Config | ✓ | ✗ | Configure cron, enable/disable, trigger manual run, view run history |
| Notifications Config | ✓ | ✗ | Set email recipients, Teams webhook, toggle channels, test send |
| **LLM Configuration** | ✓ | ✗ | Provider, API key, model, temperature, prompt templates editor |
| **Scraper Configuration** | ✓ | ✗ | Registry URLs, timeouts, rate limits, circuit breaker thresholds |
| **System Health** | ✓ | ✓ | All service health, DB stats, last pipeline run summary |
| User Management | ✓ | ✗ | Add/edit/deactivate user accounts and roles |

**Endpoints consumed:**
- All via `http://api-gateway:8000/*` (internal Docker network)
- Login: `POST /auth/token` → stores JWT in Streamlit session state

---

## 3. Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| Language | Python | 3.12 | All services |
| Web Framework | FastAPI | 0.115.x | REST API for every service |
| ASGI Server | Uvicorn | 0.32.x | Production-grade ASGI server |
| ORM | SQLAlchemy | 2.x | DB access with async support |
| DB | SQLite | 3.x | Library management data store |
| DB Migrations | Alembic | 1.14.x | Schema version control |
| Data Validation | Pydantic v2 | 2.x | Request/response models |
| HTTP Client | HTTPX | 0.27.x | Async external API calls |
| Retry Logic | Tenacity | 9.x | Retry with backoff |
| Scheduling | APScheduler | 3.10.x | Cron-based pipeline scheduler |
| Email | aiosmtplib | 3.x | Async SMTP sending |
| Templating | Jinja2 | 3.x | Email and Teams content templates |
| Security | python-jose | 3.x | JWT token handling |
| Security | passlib | 1.x | Password hashing |
| Rate Limiting | slowapi | 0.1.x | API rate limiter |
| Config | pydantic-settings | 2.x | `.env` + environment config |
| Logging | structlog | 24.x | Structured JSON logging |
| Testing | pytest + pytest-asyncio | 8.x | Unit + async tests |
| Testing | httpx TestClient | — | FastAPI test client |
| Coverage | pytest-cov | 5.x | Test coverage reports |
| Linting | ruff | 0.6.x | Fast Python linter + formatter |
| Type Checking | mypy | 1.11.x | Static type analysis |
| Containerization | Docker | 27.x | Service containers |
| Orchestration | Docker Compose | 2.x | Multi-service local dev + deploy |
| Version Parsing | packaging | 24.x | Semantic version comparison |
| UI Framework | Streamlit | 1.35.x | Interactive web dashboard (Python-native) |
| UI Data Display | pandas + st.dataframe | 2.x | Tabular library data with sorting/filtering |
| UI Charts | Plotly Express | 5.x | Status distribution pie chart, version history bar chart |
| LLM — OpenAI | openai | 1.x | OpenAI / Azure OpenAI API client |
| LLM — Anthropic | anthropic | 0.28.x | Claude API client |
| LLM — Local | ollama | 0.3.x | Local Ollama HTTP client (no external API key needed) |
| LLM — Abstraction | litellm | 1.x | Single interface across OpenAI/Azure/Anthropic/Ollama |
| Crypto | cryptography | 42.x | AES-256 encryption for LLM API key at rest in DB |
| CI (optional) | GitHub Actions | — | Automated test + build pipeline |

---

## 4. Design Patterns Applied

### 4.1 Repository Pattern — `library-data-service`

Abstracts all DB access behind a repository interface. Services never call SQLAlchemy directly — they call a repository method. This decouples business logic from persistence.

```python
# Pattern structure
class LibraryRepository(ABC):
    @abstractmethod
    async def get_all(self, filters: LibraryFilter) -> list[Library]: ...
    @abstractmethod
    async def get_by_id(self, library_id: int) -> Library | None: ...
    @abstractmethod
    async def update(self, library_id: int, data: LibraryUpdate) -> Library: ...

class SQLiteLibraryRepository(LibraryRepository):
    def __init__(self, session: AsyncSession): ...
    async def get_all(self, filters) -> list[Library]: ...  # SQLAlchemy impl
```

---

### 4.2 Strategy Pattern — `scraper-service` (Multi-Framework Extensibility Core)

Each package registry has a different API. The Strategy pattern is the **primary extensibility point** of the system — adding support for an entirely new language ecosystem requires only a new strategy class, with zero changes to any other service.

```python
class ScraperStrategy(ABC):
    @abstractmethod
    async def fetch(self, package: str) -> ScrapedVersion: ...
    
    @property
    @abstractmethod
    def registry_key(self) -> str: ...    # 'maven'|'cocoapods'|'npm'|'pypi'|...

# MVP strategies (v1)
class MavenCentralScraper(ScraperStrategy): ...    # Android / Java
class CocoaPodsScraper(ScraperStrategy): ...       # iOS pods
class SwiftPackageIndexScraper(ScraperStrategy): ... # iOS SPM
class GitHubReleasesScraper(ScraperStrategy): ...  # Vendored/binary
class CustomHTTPScraper(ScraperStrategy): ...      # Admin-configured URL

# Planned strategies (v2+) — drop-in, no other code changes
# class NpmScraper(ScraperStrategy): ...          # JavaScript/TypeScript
# class PyPIScraper(ScraperStrategy): ...         # Python
# class NuGetScraper(ScraperStrategy): ...        # C#/.NET
# class PubDevScraper(ScraperStrategy): ...       # Dart/Flutter

class ScraperFactory:
    # Dynamically loads strategies — new ones registered via scraper_registry_config
    _registry: dict[str, ScraperStrategy] = {}

    @classmethod
    def register(cls, key: str, strategy: ScraperStrategy) -> None:
        cls._registry[key] = strategy

    @classmethod
    def get(cls, registry_key: str) -> ScraperStrategy:
        if registry_key not in cls._registry:
            raise ValueError(f"No scraper registered for '{registry_key}'")
        return cls._registry[registry_key]

# Bootstrap at startup (strategy auto-discovery)
ScraperFactory.register('maven',     MavenCentralScraper())
ScraperFactory.register('cocoapods', CocoaPodsScraper())
ScraperFactory.register('github',    GitHubReleasesScraper())
ScraperFactory.register('custom',    CustomHTTPScraper())
# Adding npm in v2: ScraperFactory.register('npm', NpmScraper())
```

---

### 4.3 Circuit Breaker Pattern — `scraper-service`

Prevents cascading failures when external registries are unavailable. After N failures, the circuit opens and fast-fails for a cooldown period.

```python
# Using tenacity + custom circuit breaker state
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60): ...
    async def call(self, fn: Callable, *args) -> Any: ...
    # States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing)
```

---

### 4.4 Chain of Responsibility — `scheduler-service`

Each pipeline step is a handler. The scheduler chains them. Each step passes its output to the next. Any step can short-circuit with an error and log it without stopping the rest.

```python
class PipelineStep(ABC):
    def set_next(self, step: 'PipelineStep') -> 'PipelineStep': ...
    @abstractmethod
    async def handle(self, context: PipelineContext) -> PipelineContext: ...

class FetchLibrariesStep(PipelineStep): ...
class ScrapeVersionsStep(PipelineStep): ...
class CompareVersionsStep(PipelineStep): ...
class GenerateRecommendationsStep(PipelineStep): ...
class SendNotificationsStep(PipelineStep): ...
```

---

### 4.5 Template Method Pattern — `recommendation-service` and `notification-service`

Base class defines the algorithm skeleton. Subclasses fill in the specific steps.

```python
# Recommendation generator skeleton
class RecommendationGenerator(ABC):
    async def generate(self, comparison: ComparisonResult) -> Recommendation:
        assessment = self._assess_upgrade(comparison)    # abstract
        pros_up   = self._pros_upgrading(comparison)     # abstract
        cons_up   = self._cons_upgrading(comparison)     # abstract
        pros_no   = self._pros_not_upgrading(comparison) # abstract
        cons_no   = self._cons_not_upgrading(comparison) # abstract
        return self._build_recommendation(assessment, pros_up, cons_up, pros_no, cons_no)
```

---

### 4.6 Factory Pattern — `recommendation-service`

Selects the correct `RecommendationGenerator` based on library status and update_needed flag.

```python
class RecommendationGeneratorFactory:
    @staticmethod
    def get(library: Library) -> RecommendationGenerator:
        if library.status == 'Deprecated':
            return DeprecatedLibraryGenerator()
        if library.update_needed == 'Mandatory':
            return MandatoryUpgradeGenerator()
        if library.update_needed == 'Recommended':
            return RecommendedUpgradeGenerator()
        return SufficientVersionGenerator()
```

---

### 4.7 Facade Pattern — `api-gateway`

Hides the complexity of six internal services behind a single unified API surface. Clients only talk to port 8000.

---

### 4.8 DTO Pattern (Data Transfer Objects) — all services

Pydantic v2 models serve as DTOs. Strict separation between:
- **Request models** — validated input (no ORM objects exposed)
- **Response models** — safe output (no internal fields leaked)
- **Domain models** — SQLAlchemy ORM models (never sent over the wire)

---

## 5. Folder & File Structure

```
lib-management-app/
│
├── services/
│   │
│   ├── library-data-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   ├── main.py                  ← FastAPI app entry point
│   │   │   ├── config.py                ← pydantic-settings config
│   │   │   ├── database.py              ← SQLAlchemy async engine + session
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── orm.py               ← SQLAlchemy ORM models
│   │   │   │   └── schemas.py           ← Pydantic request/response DTOs
│   │   │   ├── repositories/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py              ← Abstract repository interface
│   │   │   │   └── library_repo.py      ← SQLite implementation
│   │   │   ├── services/
│   │   │   │   └── library_service.py   ← Business logic layer
│   │   │   ├── routers/
│   │   │   │   ├── libraries.py         ← /libraries endpoints
│   │   │   │   ├── version_history.py   ← /version-history endpoints
│   │   │   │   └── health.py            ← /health endpoint
│   │   │   └── exceptions.py            ← custom exception classes
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_library_repo.py
│   │       └── test_routers.py
│   │
│   ├── scraper-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   └── schemas.py           ← ScrapeRequest, ScrapedVersion DTOs
│   │   │   ├── strategies/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py              ← ScraperStrategy ABC
│   │   │   │   ├── maven.py             ← MavenCentralScraper
│   │   │   │   ├── cocoapods.py         ← CocoaPodsScraper
│   │   │   │   ├── github_releases.py   ← GitHubReleasesScraper
│   │   │   │   └── custom_http.py       ← CustomHTTPScraper (ACI, Scandit, etc.)
│   │   │   ├── factory.py               ← ScraperFactory
│   │   │   ├── circuit_breaker.py       ← CircuitBreaker implementation
│   │   │   ├── services/
│   │   │   │   └── scraper_service.py   ← orchestrates strategies
│   │   │   └── routers/
│   │   │       ├── scrape.py
│   │   │       └── health.py
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_maven.py
│   │       ├── test_cocoapods.py
│   │       └── test_scraper_service.py
│   │
│   ├── comparison-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   └── schemas.py           ← ComparisonRequest, ComparisonResult DTOs
│   │   │   ├── services/
│   │   │   │   ├── aggregation.py       ← merges DB data + scraped data
│   │   │   │   └── comparison.py        ← semver comparison logic
│   │   │   ├── routers/
│   │   │   │   ├── compare.py
│   │   │   │   └── health.py
│   │   │   └── clients/
│   │   │       ├── library_client.py    ← HTTP client for library-data-service
│   │   │       └── scraper_client.py    ← HTTP client for scraper-service
│   │   └── tests/
│   │       ├── test_comparison.py
│   │       └── test_aggregation.py
│   │
│   ├── recommendation-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   └── schemas.py
│   │   │   ├── generators/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py              ← RecommendationGenerator ABC (Template Method)
│   │   │   │   ├── deprecated.py        ← DeprecatedLibraryGenerator
│   │   │   │   ├── mandatory.py         ← MandatoryUpgradeGenerator
│   │   │   │   ├── recommended.py       ← RecommendedUpgradeGenerator
│   │   │   │   └── sufficient.py        ← SufficientVersionGenerator
│   │   │   ├── factory.py               ← RecommendationGeneratorFactory
│   │   │   ├── services/
│   │   │   │   └── recommendation_service.py
│   │   │   └── routers/
│   │   │       ├── recommendations.py
│   │   │       └── health.py
│   │   └── tests/
│   │       ├── test_generators.py
│   │       └── test_factory.py
│   │
│   ├── notification-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   └── schemas.py
│   │   │   ├── channels/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py              ← NotificationChannel ABC
│   │   │   │   ├── email_channel.py     ← SMTP/SendGrid implementation
│   │   │   │   └── teams_channel.py     ← Teams Webhook implementation
│   │   │   ├── templates/
│   │   │   │   ├── email_summary.html   ← Jinja2 HTML email template
│   │   │   │   ├── email_summary.txt    ← plain text fallback
│   │   │   │   └── teams_card.json      ← Teams Adaptive Card template
│   │   │   ├── services/
│   │   │   │   └── notification_service.py
│   │   │   └── routers/
│   │   │       ├── notify.py
│   │   │       └── health.py
│   │   └── tests/
│   │       ├── test_email_channel.py
│   │       └── test_teams_channel.py
│   │
│   ├── scheduler-service/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   └── schemas.py
│   │   │   ├── pipeline/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── context.py           ← PipelineContext dataclass
│   │   │   │   ├── base_step.py         ← PipelineStep ABC
│   │   │   │   ├── fetch_libraries.py
│   │   │   │   ├── scrape_versions.py
│   │   │   │   ├── compare_versions.py
│   │   │   │   ├── generate_recommendations.py
│   │   │   │   └── send_notifications.py
│   │   │   ├── services/
│   │   │   │   └── scheduler.py         ← APScheduler setup + pipeline runner
│   │   │   └── routers/
│   │   │       ├── schedule.py
│   │   │       └── health.py
│   │   └── tests/
│   │       └── test_pipeline.py
│   │
│   └── api-gateway/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── pyproject.toml
│       ├── src/
│       │   ├── main.py
│       │   ├── config.py
│       │   ├── auth/
│       │   │   ├── jwt_handler.py       ← token creation + validation
│       │   │   └── dependencies.py      ← FastAPI dependency injection for auth
│       │   ├── middleware/
│       │   │   ├── rate_limiter.py      ← slowapi rate limiting
│       │   │   └── logging_middleware.py
│       │   └── routers/
│       │       └── proxy.py             ← routes to downstream services
│       └── tests/
│           └── test_auth.py
│
├── shared/                              ← shared utilities (not a running service)
│   ├── models/
│   │   └── base_schemas.py             ← common Pydantic base models
│   ├── utils/
│   │   ├── version_parser.py           ← semantic version utilities
│   │   └── http_client.py              ← base HTTPX async client wrapper
│   └── config/
│       └── base_settings.py            ← common pydantic-settings base
│
├── docker/
│   ├── docker-compose.yml              ← production multi-service compose
│   ├── docker-compose.dev.yml          ← development overrides (hot reload)
│   └── .env.example                    ← environment variable template
│
├── db/
│   └── library_management.db          ← existing SQLite DB (119 libraries)
│
├── migrations/                         ← Alembic DB migrations
│   ├── env.py
│   ├── alembic.ini
│   └── versions/
│       └── 001_initial_schema.py
│
│
├── services/ui-service/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── src/
│   │   ├── app.py                       ← Streamlit entry point (st.set_page_config)
│   │   ├── config.py                    ← API Gateway base URL, settings
│   │   ├── auth/
│   │   │   ├── login.py                 ← Login page + JWT session management
│   │   │   └── session.py               ← session_state helpers, role checks
│   │   ├── api/
│   │   │   ├── client.py                ← HTTPX client wrapper (attaches JWT header)
│   │   │   ├── libraries.py             ← API calls for library data
│   │   │   ├── scheduler.py             ← API calls for schedule config + run history
│   │   │   ├── notifications.py         ← API calls for notification config
│   │   │   ├── llm_config.py            ← API calls for LLM config + prompt templates
│   │   │   ├── scraper_config.py        ← API calls for scraper registry config
│   │   │   └── health.py                ← API calls for service health status
│   │   ├── pages/
│   │   │   ├── 1_Dashboard.py           ← summary metrics + full library table
│   │   │   ├── 2_Library_Detail.py      ← per-library detail, version history, rec
│   │   │   ├── 3_Management.py          ← [Admin] edit library, add URL, set reason
│   │   │   ├── 4_Scheduler_Config.py    ← [Admin] cron config, manual run, run history
│   │   │   ├── 5_Notifications_Config.py ← [Admin] email/teams config + test send
│   │   │   ├── 6_LLM_Config.py          ← [Admin] LLM provider, key, model, prompts
│   │   │   ├── 7_Scraper_Config.py      ← [Admin] registry URLs, timeouts, rate limits
│   │   │   ├── 8_System_Health.py       ← [Both] service health + DB stats
│   │   │   └── 9_User_Management.py     ← [Admin] user accounts + role assignment
│   │   ├── components/
│   │   │   ├── library_table.py         ← reusable color-coded st.dataframe component
│   │   │   ├── metrics_row.py           ← summary KPI metric cards
│   │   │   ├── status_badge.py          ← color badge for status / update_needed
│   │   │   └── sidebar.py               ← navigation + logout + current user display
│   │   └── utils/
│   │       └── formatters.py            ← date formatting, version display helpers
│   └── tests/
│       ├── test_api_client.py
│       └── test_formatters.py
│
└── Makefile                            ← dev convenience commands
```

---

## 6. Database Design

The existing `library_management.db` SQLite database (already populated with 119 libraries) is the single data store, accessed only by `library-data-service`. All other services communicate with the DB indirectly through HTTP calls to `library-data-service`.

### Existing Tables (already created)
- `libraries` — core library metadata
- `version_history` — version tracking over time
- `recommendations` — generated guidance
- `notifications` — delivery log
- `scrape_log` — scrape run history

### New Tables to Add (via Alembic migration)

```sql
-- User accounts for UI persona-based login
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE,
    email       TEXT NOT NULL UNIQUE,
    full_name   TEXT,
    hashed_password TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'viewer'
                CHECK(role IN ('admin','viewer')),
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    last_login  TEXT
);

-- LLM provider and model configuration (single active row)
CREATE TABLE llm_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider        TEXT NOT NULL DEFAULT 'openai'
                    CHECK(provider IN ('openai','azure_openai','anthropic','ollama')),
    model_name      TEXT NOT NULL DEFAULT 'gpt-4o',
    api_base_url    TEXT,                    -- required for Azure OpenAI and Ollama
    api_key_encrypted TEXT,                  -- AES-256 encrypted; NULL for Ollama
    api_version     TEXT,                    -- required for Azure OpenAI (e.g. 2024-02-01)
    temperature     REAL NOT NULL DEFAULT 0.3,
    max_tokens      INTEGER NOT NULL DEFAULT 1024,
    timeout_seconds INTEGER NOT NULL DEFAULT 30,
    enabled         INTEGER NOT NULL DEFAULT 1,
    updated_by      TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Editable LLM prompt templates (one row per use-case)
CREATE TABLE llm_prompt_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_key      TEXT NOT NULL UNIQUE,
                    -- VALUES:
                    -- 'system_prompt'         base system role prompt
                    -- 'upgrade_pros'          generate pros of upgrading
                    -- 'upgrade_cons'          generate cons of upgrading
                    -- 'no_upgrade_pros'       generate pros of staying
                    -- 'no_upgrade_cons'       generate cons of staying
                    -- 'recommendation_summary' one-paragraph overall summary
                    -- 'email_subject'         email subject line template
                    -- 'email_intro'           email body opening paragraph
                    -- 'teams_title'           Teams card title template
    template_text   TEXT NOT NULL,           -- Jinja2-style template with {variables}
    variables_hint  TEXT,                    -- JSON list of available variables
    version         INTEGER NOT NULL DEFAULT 1,
    updated_by      TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Per-registry scraper configuration (supports any future ecosystem)
CREATE TABLE scraper_registry_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    registry_key    TEXT NOT NULL UNIQUE,
                    -- MVP: 'maven'|'cocoapods'|'spm'|'github'|'custom'
                    -- v2+: 'npm'|'pypi'|'nuget'|'pubdev'|'gradle'|'go'|'crates'|'rubygems'
    display_name    TEXT NOT NULL,           -- human-readable name shown in UI
    ecosystem       TEXT NOT NULL DEFAULT 'mobile',
                    -- VALUES: 'mobile'|'web'|'backend'|'cross-platform'|'devops'|'data'
    framework_language TEXT,                 -- 'kotlin'|'swift'|'javascript'|'python'|'csharp'|'dart'|...
    base_url        TEXT,                    -- override default registry API URL
    timeout_seconds INTEGER NOT NULL DEFAULT 10,
    rate_limit_per_min INTEGER NOT NULL DEFAULT 60,
    max_retries     INTEGER NOT NULL DEFAULT 3,
    circuit_breaker_threshold INTEGER NOT NULL DEFAULT 5,
    circuit_breaker_cooldown  INTEGER NOT NULL DEFAULT 60,
    custom_headers  TEXT,                    -- JSON object of extra headers
    strategy_class  TEXT,                    -- Python class name for dynamic loading (future)
    release_phase   TEXT NOT NULL DEFAULT 'mvp'
                    CHECK(release_phase IN ('mvp','v2','v3','v4','v5','future')),
    enabled         INTEGER NOT NULL DEFAULT 1,
    updated_by      TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
    -- SEED ROWS (MVP):
    -- ('maven',     'Maven Central',      'mobile',   'kotlin',     ...)
    -- ('cocoapods', 'CocoaPods',          'mobile',   'swift',      ...)
    -- ('spm',       'Swift Package Index','mobile',   'swift',      ...)
    -- ('github',    'GitHub Releases',    'mobile',   NULL,         ...)
    -- ('custom',    'Custom HTTP',        'mobile',   NULL,         ...)
    -- PLANNED ROWS (add when phase reached):
    -- ('npm',    'npm Registry',    'web',     'javascript', ..., 'v2')
    -- ('pypi',   'PyPI',            'backend', 'python',     ..., 'v2')
    -- ('nuget',  'NuGet Gallery',   'backend', 'csharp',     ..., 'v3')
    -- ('pubdev', 'pub.dev',         'mobile',  'dart',       ..., 'v3')
    -- ('gradle', 'Gradle Plugins',  'devops',  'kotlin',     ..., 'v4')
);

-- Libraries platform/ecosystem expansion (Alembic migration adds these columns)
-- ALTER TABLE libraries ADD COLUMN ecosystem TEXT DEFAULT 'mobile';
--   VALUES: 'mobile'|'web'|'backend'|'cross-platform'|'devops'
-- ALTER TABLE libraries ADD COLUMN framework_language TEXT;
--   VALUES: 'kotlin'|'java'|'swift'|'objc'|'javascript'|'typescript'|
--           'python'|'csharp'|'dart'|'go'|'rust'|'ruby'
-- NOTE: 'platform' column (Android/iOS/Both) remains for backward compat;
--       new columns add ecosystem-level metadata for multi-framework support.

-- General application key-value settings
CREATE TABLE app_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    is_sensitive    INTEGER NOT NULL DEFAULT 0,  -- 1 = mask in UI
    updated_by      TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
    -- SEED ROWS:
    -- ('smtp_host', '', 'SMTP server hostname', 0)
    -- ('smtp_port', '587', 'SMTP port', 0)
    -- ('smtp_username', '', 'SMTP auth username', 0)
    -- ('smtp_password_encrypted', '', 'SMTP password (encrypted)', 1)
    -- ('smtp_from', '', 'From email address', 0)
    -- ('email_recipients', '[]', 'JSON array of email recipients', 0)
    -- ('teams_webhook_url', '', 'Teams Incoming Webhook URL', 1)
    -- ('teams_enabled', '1', 'Enable Teams notifications', 0)
    -- ('email_enabled', '1', 'Enable email notifications', 0)
    -- ('github_token_encrypted', '', 'GitHub API token (encrypted)', 1)
    -- ('schedule_cron', '0 8 * * 1', 'Pipeline cron schedule', 0)
    -- ('schedule_enabled', '1', 'Enable scheduled pipeline', 0)
);

-- Library update audit log (who updated, when, why)
CREATE TABLE library_update_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id      INTEGER NOT NULL REFERENCES libraries(id),
    updated_by      TEXT NOT NULL,          -- username
    update_type     TEXT NOT NULL,          -- 'manual'|'scheduler'|'scraper'
    field_changed   TEXT NOT NULL,          -- 'current_version'|'status'|'external_url' etc.
    old_value       TEXT,
    new_value       TEXT,
    reason          TEXT,                   -- human-readable reason entered by Admin
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Custom external URL registry (Admin-configurable per library)
CREATE TABLE library_external_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id      INTEGER NOT NULL REFERENCES libraries(id),
    source_name     TEXT NOT NULL,           -- display name e.g. "Release Notes Page"
    url             TEXT NOT NULL,           -- external URL
    source_type     TEXT NOT NULL DEFAULT 'custom'
                    CHECK(source_type IN ('registry','release_notes','changelog','docs','custom')),
    added_by        TEXT NOT NULL,           -- username of Admin who added it
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Pipeline run tracking
CREATE TABLE pipeline_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL UNIQUE,        -- UUID
    triggered_by TEXT NOT NULL,              -- 'scheduler' | 'manual'
    status      TEXT NOT NULL DEFAULT 'running'
                CHECK(status IN ('running','completed','partial','failed')),
    libraries_processed INTEGER DEFAULT 0,
    libraries_updated   INTEGER DEFAULT 0,
    errors_count        INTEGER DEFAULT 0,
    started_at  TEXT DEFAULT (datetime('now')),
    finished_at TEXT
);

-- Per-library scrape result within a pipeline run
CREATE TABLE pipeline_run_details (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    library_id  INTEGER REFERENCES libraries(id),
    step        TEXT NOT NULL,              -- 'scrape'|'compare'|'recommend'|'notify'
    status      TEXT NOT NULL,
    message     TEXT,
    recorded_at TEXT DEFAULT (datetime('now'))
);

-- Notification schedule configuration
CREATE TABLE notification_schedule (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cron_expression TEXT NOT NULL DEFAULT '0 8 * * 1',  -- Monday 8am
    enabled         INTEGER NOT NULL DEFAULT 1,
    channels        TEXT NOT NULL DEFAULT 'both',       -- 'email'|'teams'|'both'
    email_recipients TEXT,                               -- JSON array
    teams_webhook_url TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- ── TABLES ADDED FROM BUSINESS & TECHNICAL GAPS (Sections 19–20) ────────────

-- B1: Upgrade lifecycle tracking per library recommendation
CREATE TABLE upgrade_lifecycle (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id        INTEGER NOT NULL REFERENCES libraries(id),
    recommendation_id INTEGER REFERENCES recommendations(id),
    status            TEXT NOT NULL DEFAULT 'Pending'
                      CHECK(status IN ('Pending','Acknowledged','Scheduled',
                                       'In Progress','Completed','Skipped')),
    target_version    TEXT,
    target_sprint     TEXT,
    target_date       TEXT,
    completed_version TEXT,
    skip_reason       TEXT,
    actioned_by       TEXT,
    created_at        TEXT DEFAULT (datetime('now')),
    updated_at        TEXT DEFAULT (datetime('now'))
);

-- B2: Notification deduplication — track what was last sent per library
CREATE TABLE notification_sent_log (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id             INTEGER NOT NULL REFERENCES libraries(id),
    notification_id        INTEGER REFERENCES notifications(id),
    latest_version_at_send TEXT,
    update_needed_at_send  TEXT,
    status_at_send         TEXT,
    content_hash           TEXT NOT NULL,   -- SHA-256; resend only if changed
    sent_at                TEXT DEFAULT (datetime('now'))
);

-- B3: Bulk library import job tracking
CREATE TABLE bulk_import_job (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT NOT NULL UNIQUE,
    import_format TEXT NOT NULL,            -- 'requirements_txt'|'pom_xml'|'podfile'|'csv'|...
    filename      TEXT NOT NULL,
    total_rows    INTEGER DEFAULT 0,
    imported      INTEGER DEFAULT 0,
    skipped       INTEGER DEFAULT 0,
    failed        INTEGER DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'processing'
                  CHECK(status IN ('processing','completed','failed')),
    error_log     TEXT,
    imported_by   TEXT NOT NULL,
    created_at    TEXT DEFAULT (datetime('now')),
    finished_at   TEXT
);

-- B4: Application team definitions and library ownership
CREATE TABLE application_teams (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name     TEXT NOT NULL UNIQUE,
    team_email    TEXT,
    teams_channel TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE library_ownership (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id  INTEGER NOT NULL REFERENCES libraries(id),
    team_id     INTEGER NOT NULL REFERENCES application_teams(id),
    is_primary  INTEGER NOT NULL DEFAULT 1,
    assigned_by TEXT NOT NULL,
    assigned_at TEXT DEFAULT (datetime('now')),
    UNIQUE(library_id, team_id)
);

-- T1: Scraper result cache with TTL
CREATE TABLE scrape_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id      INTEGER NOT NULL REFERENCES libraries(id),
    registry_key    TEXT NOT NULL,
    scraped_version TEXT NOT NULL,
    release_notes   TEXT,
    raw_response    TEXT,
    expires_at      TEXT NOT NULL,
    scraped_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(library_id, registry_key)
);

-- T5: LLM token usage and cost tracking per pipeline run
CREATE TABLE llm_usage_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT REFERENCES pipeline_runs(run_id),
    library_id          INTEGER REFERENCES libraries(id),
    prompt_key          TEXT,
    model               TEXT NOT NULL,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    total_tokens        INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd  REAL DEFAULT 0.0,
    latency_ms          INTEGER,
    logged_at           TEXT DEFAULT (datetime('now'))
);

-- Immutability triggers for library_update_log (T11)
CREATE TRIGGER audit_log_immutable_update
    BEFORE UPDATE ON library_update_log
BEGIN
    SELECT RAISE(ABORT, 'library_update_log is immutable');
END;

CREATE TRIGGER audit_log_immutable_delete
    BEFORE DELETE ON library_update_log
BEGIN
    SELECT RAISE(ABORT, 'library_update_log is immutable');
END;

-- B7: Alert priority columns added to libraries (via Alembic migration)
-- ALTER TABLE libraries ADD COLUMN alert_priority TEXT DEFAULT 'Normal'
--     CHECK(alert_priority IN ('Normal','High','Critical'));
-- ALTER TABLE libraries ADD COLUMN deadline_date  TEXT;
-- ALTER TABLE libraries ADD COLUMN deadline_notes TEXT;
```

---

## 7. API Contracts

All services use **JSON** request/response bodies. All responses follow this envelope:

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "service": "library-data-service",
    "version": "1.0.0",
    "timestamp": "2026-06-25T08:00:00Z"
  }
}
```

Error response:
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "LIBRARY_NOT_FOUND",
    "message": "Library with id=999 does not exist",
    "detail": null
  },
  "meta": { ... }
}
```

### 7.1 Library Data Service — key contracts

**GET /libraries**
```
Query params: platform=Android|iOS, status=Active|Deprecated|Legacy, update_needed=Mandatory|Recommended|None, skip=0, limit=100
Response: { "data": { "libraries": [Library], "total": 119 } }
```

**PUT /libraries/{id}**
```json
{
  "current_version": "3.18.0",
  "status": "Active",
  "last_checked_date": "2026-06-25"
}
```

### 7.2 Scraper Service — key contracts

**POST /scrape/batch**
```json
{
  "libraries": [
    { "id": 1, "package": "com.adobe.marketing.mobile:sdk-bom", "registry": "maven", "repo_url": "sdk-bom" }
  ]
}
```
Response:
```json
{
  "data": {
    "results": [
      { "library_id": 1, "package": "com.adobe.marketing.mobile:sdk-bom", "latest_version": "3.18.0", "release_notes": "...", "scraped_at": "2026-06-25T08:01:00Z", "status": "success" }
    ],
    "failed": []
  }
}
```

### 7.3 Comparison Service — key contracts

**POST /compare/batch**
```json
{
  "library_ids": [1, 2, 3]
}
```
Response:
```json
{
  "data": {
    "comparisons": [
      { "library_id": 1, "current_version": "3.6.0", "latest_version": "3.18.0", "new_version_released": true, "version_delta": "major", "comparison_date": "2026-06-25" }
    ]
  }
}
```

### 7.4 Recommendation Service — key contracts

**POST /recommendations/generate/batch**
```json
{ "library_ids": [1, 2, 3] }
```
Response:
```json
{
  "data": {
    "recommendations": [
      {
        "library_id": 1,
        "upgrade_recommended": "Yes",
        "summary": "Adobe Analytics BOM has a new major version (3.18.0). Upgrade is mandatory (PI 31).",
        "upgrade_pros": ["New BOM consolidates all Adobe SDK versions", "Security patches included"],
        "upgrade_cons": ["Major version bump — check for breaking changes in release notes"],
        "no_upgrade_pros": ["No immediate disruption to existing integration"],
        "no_upgrade_cons": ["Missing security updates", "Out of sync with PI 31 mandate"]
      }
    ]
  }
}
```

---

## 8. Inter-Service Communication

All communication is **synchronous HTTP** over Docker internal network using service names as hostnames.

| Caller | Calls | Via |
|--------|-------|-----|
| scheduler-service | library-data-service | `http://library-data-service:8001` |
| scheduler-service | scraper-service | `http://scraper-service:8002` |
| scheduler-service | comparison-service | `http://comparison-service:8003` |
| scheduler-service | recommendation-service | `http://recommendation-service:8004` |
| scheduler-service | notification-service | `http://notification-service:8005` |
| api-gateway | all services | `http://{service-name}:{port}` |

**Future option:** Replace HTTP polling with an **event queue** (Redis Streams or RabbitMQ) for fully async pipeline — out of scope for v1.

---

## 9. Security Design

### 9.1 Authentication — Persona-Based Login + JWT

**Two personas:**

| Persona | Role value | Capabilities |
|---------|-----------|-------------|
| **Admin** | `admin` | Full access: view + manage libraries, configure scheduler, set notification channels, add external URLs, manage users |
| **Viewer** | `viewer` | Read-only: view dashboard, library details, version history, recommendations |

**Login flow (UI → API Gateway):**
```
Streamlit Login Page
  → POST /auth/token  {username, password}
  → API Gateway validates credentials against `users` table (bcrypt hash)
  → Returns JWT {sub: username, role: admin|viewer, exp: ...}
  → JWT stored in st.session_state
  → All subsequent API calls include: Authorization: Bearer <token>
  → API Gateway decodes JWT, injects X-User-Role header to downstream services
  → Downstream services enforce role on sensitive write endpoints
```

**Role enforcement:**
- Read endpoints (`GET`): accessible by both Admin and Viewer
- Write/config endpoints (`POST`, `PUT`, `DELETE` on schedule, notifications, users, library management): Admin only → returns 403 if Viewer token
- Streamlit pages: `session.py` checks `st.session_state.role` before rendering Admin-only pages → redirects to Dashboard if Viewer

**Default admin account:** seeded at DB migration time (credentials in `.env`), must be changed on first login.

```
External request → API Gateway → validate JWT → check role → route to service
                                             ↓
                                         401 if expired
                                         403 if role insufficient
```

### 9.2 Internal Service-to-Service

- Services communicate over Docker internal bridge network (not exposed to host)
- Internal calls use a shared `X-Internal-Service-Key` header (pre-shared secret from env)
- No JWT required for internal calls

### 9.3 Secrets Management

- All secrets stored in `.env` files (never committed to source control)
- `.env.example` committed as template with no real values
- In production: use Docker secrets or environment injection
- No hardcoded credentials anywhere in source

```
Required .env variables:
  JWT_SECRET_KEY=
  INTERNAL_SERVICE_KEY=
  SMTP_HOST=
  SMTP_PORT=
  SMTP_USERNAME=
  SMTP_PASSWORD=
  SMTP_FROM=
  TEAMS_WEBHOOK_URL=
  GITHUB_TOKEN=              ← for GitHub Releases API (rate limit: 5000/hr with token)
  SCHEDULE_CRON=0 8 * * 1
  EMAIL_RECIPIENTS=["team@org.com"]
  DEFAULT_ADMIN_USERNAME=admin
  DEFAULT_ADMIN_PASSWORD=    ← hashed with bcrypt at seed time
  API_GATEWAY_URL=http://api-gateway:8000  ← used by UI service
  DB_ENCRYPTION_KEY=         ← AES-256 key for encrypting API keys in DB
                               (32 bytes hex — generate with: python -c "import secrets; print(secrets.token_hex(32))")
```

> **All sensitive settings (LLM API key, SMTP password, GitHub token, Teams webhook)**
> are stored **encrypted in `app_settings` / `llm_config` tables** using AES-256.
> The encryption key (`DB_ENCRYPTION_KEY`) is the only secret that must remain in `.env`.
> Admins manage all other secrets through the UI — no file edits needed after initial deploy.

### 9.4 Input Validation

- All inputs validated by Pydantic v2 strict models
- Package names sanitized before use in HTTP requests (prevent SSRF)
- URL allowlist for external registry calls (no arbitrary URL fetching)
- SQL queries via SQLAlchemy ORM only (no raw SQL strings — prevents injection)

### 9.5 Rate Limiting (API Gateway)

- Default: 100 requests/minute per IP for external endpoints
- Scheduler service account: exempt from rate limiting via service key

### 9.6 HTTPS

- In production: place an nginx reverse proxy in front of the API Gateway with TLS termination
- Internal Docker network: HTTP only (TLS overhead not needed internally)

### 9.7 Dependency Security

- `pip-audit` runs on all `requirements.txt` in CI pipeline
- Pin all dependencies to exact versions (no `>=` ranges in production)
- Weekly automated dependency security scan

---

## 10. Docker & Container Strategy

### 10.1 Dockerfile per service (standard template)

```dockerfile
# Multi-stage build for minimal image size
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime
WORKDIR /app
# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ ./src/
USER appuser
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
```

### 10.2 docker-compose.yml (production)

```yaml
version: "3.9"
services:
  api-gateway:
    build: ./services/api-gateway
    ports: ["8000:8000"]
    env_file: ./docker/.env
    depends_on: [library-data-service, scraper-service, comparison-service, recommendation-service, notification-service, scheduler-service]
    networks: [lib-mgmt-net]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s

  library-data-service:
    build: ./services/library-data-service
    expose: ["8001"]
    env_file: ./docker/.env
    volumes: ["./db:/app/db:rw"]     ← SQLite file mount
    networks: [lib-mgmt-net]
    restart: unless-stopped

  scraper-service:
    build: ./services/scraper-service
    expose: ["8002"]
    env_file: ./docker/.env
    networks: [lib-mgmt-net]
    restart: unless-stopped

  comparison-service:
    build: ./services/comparison-service
    expose: ["8003"]
    env_file: ./docker/.env
    networks: [lib-mgmt-net]
    restart: unless-stopped

  recommendation-service:
    build: ./services/recommendation-service
    expose: ["8004"]
    env_file: ./docker/.env
    networks: [lib-mgmt-net]
    restart: unless-stopped

  notification-service:
    build: ./services/notification-service
    expose: ["8005"]
    env_file: ./docker/.env
    networks: [lib-mgmt-net]
    restart: unless-stopped

  scheduler-service:
    build: ./services/scheduler-service
    expose: ["8006"]
    env_file: ./docker/.env
    networks: [lib-mgmt-net]
    restart: unless-stopped

  ui-service:
    build: ./services/ui-service
    ports: ["8501:8501"]          # exposed to host — Streamlit UI
    env_file: ./docker/.env
    depends_on: [api-gateway]
    networks: [lib-mgmt-net]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/healthz"]
      interval: 30s

networks:
  lib-mgmt-net:
    driver: bridge
```

### 10.3 Exposed ports to host: `:8000` (API Gateway REST) and `:8501` (Streamlit UI). All backend services are internal-only.

---

## 11. Error Handling & Resilience

### 11.1 Retry with Exponential Backoff (scraper-service)

```python
# tenacity retry for external HTTP calls
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(httpx.TimeoutException),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)
async def fetch_with_retry(url: str) -> dict: ...
```

### 11.2 Graceful Degradation

- If scraper fails for a library → log to `scrape_log`, mark as error, continue pipeline
- If comparison fails for a library → skip recommendation for that library, continue
- If notification fails → log to `notifications` table with status='Failed', retry next run

### 11.3 Global Exception Handler (all services)

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", exc=str(exc), path=request.url.path)
    return JSONResponse(status_code=500, content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}})
```

### 11.4 Health Checks

Every service exposes `GET /health` returning:
```json
{ "status": "healthy", "service": "scraper-service", "version": "1.0.0", "db_connected": true }
```

---

## 12. Logging & Observability

### 12.1 Structured JSON Logging (structlog)

All services emit structured JSON logs to stdout. Docker captures these.

```json
{
  "timestamp": "2026-06-25T08:01:23.456Z",
  "level": "info",
  "service": "scraper-service",
  "event": "library_scraped",
  "library_id": 1,
  "package": "com.adobe.marketing.mobile:sdk-bom",
  "latest_version": "3.18.0",
  "duration_ms": 245
}
```

### 12.2 Request Logging Middleware (all services)

Logs every request: method, path, status code, duration_ms, service name.

### 12.3 Pipeline Run Logging

Every scheduler run writes to `pipeline_runs` table:
- Start time, finish time, libraries processed, errors count, status

---

## 13. Testing Strategy

### 13.1 Unit Tests (per service)

| Service | What to test |
|---------|-------------|
| library-data-service | Repository methods (in-memory SQLite), schema validation |
| scraper-service | Each strategy mock (no real HTTP calls), circuit breaker states |
| comparison-service | Semver comparison edge cases, aggregation logic |
| recommendation-service | Each generator produces correct pros/cons for given inputs |
| notification-service | Template rendering, channel formatting |
| scheduler-service | Pipeline step chaining, context passing |

### 13.2 Integration Tests

- Each service: spin up test FastAPI app + in-memory SQLite
- Test full request/response cycle including DB reads/writes
- Mock external HTTP calls with `httpx.MockTransport`

### 13.3 End-to-End Test

One test that runs the full pipeline:
```
Seeded SQLite DB → Scraper (mocked) → Comparison → Recommendation → Notification (captured)
```
Asserts recommendations exist in DB and notification content is correct.

### 13.4 Coverage Target

- Minimum 80% line coverage per service
- Run with: `pytest --cov=src --cov-report=term-missing`

### 13.5 Test Commands (Makefile)

```makefile
test:           pytest services/*/tests/ -v
test-coverage:  pytest services/*/tests/ --cov=src --cov-report=html
lint:           ruff check services/
typecheck:      mypy services/
security-scan:  pip-audit -r services/*/requirements.txt
```

---

## 14. Development Phases

> **MVP Scope (v1, Days 1–5):** Android libraries (Maven Central) + iOS libraries (CocoaPods/SPM). The architecture is built for extension from day one — future framework support (npm, PyPI, NuGet, etc.) is added by dropping in new strategy files with zero changes to other services.

### Phase 1 — Foundation [MVP] (Day 1)

**Goal:** Project scaffold + DB + Library Data Service working

Tasks:
- [ ] Set up `lib-management-app/` folder structure
- [ ] Configure `shared/` models and base settings
- [ ] Create `docker/docker-compose.yml` skeleton
- [ ] Create `migrations/` with Alembic, connect to existing `library_management.db`
- [ ] Run Alembic migration to add `pipeline_runs` and `pipeline_run_details` tables
- [ ] Build `library-data-service` fully:
  - ORM models (SQLAlchemy)
  - Pydantic DTOs
  - Repository (SQLiteLibraryRepository)
  - Service layer
  - All routers (libraries, version-history, health)
  - Unit + integration tests
  - Dockerfile
- [ ] Verify: `docker compose up library-data-service` → all 119 libraries accessible via API

Deliverable: Library Data Service container running with full test suite passing.

---

### Phase 2 — Scraping [MVP: Android + iOS] (Day 2)

**Goal:** Scraper Service fetching real latest versions from Maven Central (Android) and CocoaPods/SPM (iOS) — the two ecosystems covered in v1

Tasks:
- [ ] Build `scraper-service`:
  - `ScraperStrategy` ABC
  - `MavenCentralScraper` — calls `search.maven.org`
  - `CocoaPodsScraper` — calls `trunk.cocoapods.org`
  - `GitHubReleasesScraper` — for Gigya, Scandit, etc.
  - `CustomHTTPScraper` — for ACI/IPWorks (configured URL per library)
  - `ScraperFactory`
  - `CircuitBreaker`
  - Batch scrape endpoint
  - Tests (all strategies mocked)
  - Dockerfile
- [ ] Write library-to-registry mapping config (which library uses which scraper)
- [ ] Verify: batch scrape of 10 sample Android + 5 iOS libraries returns correct versions

Deliverable: Scraper Service fetching real data from Maven Central and CocoaPods. Strategy pattern foundation in place for future ecosystems.

---

### Phase 3 — Comparison + Recommendation [MVP] (Day 3)

**Goal:** Full comparison and recommendation pipeline operational

Tasks:
- [ ] Build `comparison-service`:
  - HTTP clients (library-data-service, scraper-service)
  - Aggregation logic
  - Semver comparison (`packaging` library)
  - DB write of comparison results via library-data-service
  - Tests
  - Dockerfile
- [ ] Build `recommendation-service`:
  - `RecommendationGenerator` ABC (Template Method)
  - Four concrete generators
  - `RecommendationGeneratorFactory`
  - DB write of recommendations
  - Tests (each generator verified against fixture data)
  - Dockerfile
- [ ] Verify: run comparison + recommendation for all 119 libraries, check DB populated

Deliverable: All 119 libraries have comparison results + recommendations in DB.

---

### Phase 4 — Notifications + Scheduler + API Gateway + Streamlit UI [MVP] (Day 4)

**Goal:** Email/Teams notifications working, scheduler running, full UI accessible with persona login

Tasks:
- [ ] Build `notification-service`:
  - Jinja2 HTML email template
  - Teams Adaptive Card template
  - `EmailChannel` (aiosmtplib)
  - `TeamsChannel` (httpx webhook POST)
  - Tests (templates rendered with fixture data)
  - Dockerfile
- [ ] Build `scheduler-service`:
  - `PipelineContext`
  - All 5 pipeline steps (Chain of Responsibility)
  - APScheduler setup + cron job
  - Manual trigger + schedule update endpoints
  - Tests (pipeline step chaining)
  - Dockerfile
- [ ] Build `api-gateway`:
  - JWT auth middleware + `/auth/token` login endpoint
  - Persona role enforcement (Admin/Viewer)
  - User management endpoints (`users` table)
  - Rate limiting + proxy routing
  - Dockerfile
- [ ] Build `ui-service` (Streamlit):
  - Login page + session state JWT management
  - Dashboard page: metrics row + color-coded library table + filters
  - Library Detail page: all fields + version history + recommendation + update log
  - Management page [Admin]: edit library, add external URL, set update reason
  - Scheduler Config page [Admin]: cron editor, enable/disable, trigger run, run history
  - Notifications Config page [Admin]: email recipients, Teams webhook, test send
  - User Management page [Admin]: add/edit users, assign roles
  - Dockerfile
- [ ] Complete `docker-compose.yml` with all 8 services
- [ ] Test full pipeline end-to-end in Docker
- [ ] Verify email received, Teams message posted, UI accessible at http://localhost:8501

Deliverable: Full pipeline running in Docker, email + Teams working, UI fully operational with Admin and Viewer login.

---

### Phase 5 — Testing, Security Hardening, Documentation [MVP Complete] (Day 5)

**Goal:** Production-ready MVP deployed — Android + iOS working end-to-end. Architecture validated for framework extension.

Tasks:
- [ ] Run full test suite with coverage report (target ≥80%)
- [ ] Run `ruff` linter + `mypy` type checker on all services
- [ ] Run `pip-audit` security scan on all requirements files
- [ ] Complete `.env.example` with all required variables documented
- [ ] Write per-service `README.md` covering:
  - Service purpose
  - Endpoints
  - Environment variables
  - How to run + test
- [ ] Final docker-compose smoke test (all services healthy)
- [ ] Hand-over documentation

Deliverable: All tests passing, security clean, Docker deployment verified.

---

### Phase 6 — npm / Node.js Framework Support (v2)

**Goal:** Extend library management to cover JavaScript/TypeScript libraries tracked by the organization

Tasks:
- [ ] Create `strategies/npm.py` — `NpmScraper` calling `registry.npmjs.org/{package}`
- [ ] Add npm row to `scraper_registry_config` DB table
- [ ] Add `ecosystem` and `framework_language` columns to `libraries` table (Alembic migration)
- [ ] Import npm library list (CSV/Excel or manual entry via UI Management page)
- [ ] Verify: batch scrape of npm libraries returns correct `latest` versions
- [ ] Update UI Scraper Config page to show npm registry config
- [ ] Update Dashboard filters to include `ecosystem` filter (Web/Mobile/Backend)
- [ ] End-to-end test: npm library → scrape → compare → recommend → notify

Deliverable: npm libraries visible in dashboard alongside Android/iOS, same pipeline.

---

### Phase 7 — PyPI / Python Framework Support (v2)

**Goal:** Extend to Python libraries used across backend services

Tasks:
- [ ] Create `strategies/pypi.py` — `PyPIScraper` calling `pypi.org/pypi/{package}/json`
- [ ] Add pypi row to `scraper_registry_config`
- [ ] Import Python library list (from requirements.txt files or manual)
- [ ] Verify batch scrape of PyPI packages
- [ ] End-to-end test

Deliverable: Python libraries in dashboard + recommendations.

---

### Phase 8 — NuGet + Dart/Flutter Support (v3)

**Goal:** Cover .NET and Flutter/Dart ecosystems

Tasks:
- [ ] Create `strategies/nuget.py` — `NuGetScraper` calling `api.nuget.org`
- [ ] Create `strategies/pubdev.py` — `PubDevScraper` calling `pub.dev/api/packages`
- [ ] Add nuget + pubdev rows to `scraper_registry_config`
- [ ] Import .NET and Flutter library lists
- [ ] End-to-end test for both

Deliverable: NuGet and pub.dev libraries fully supported.

---

### Phase 9+ — Organization-Wide Any-Framework Coverage (v4/v5/Future)

**Goal:** Make the system the single source of truth for all library versions across the entire organization

Approach:
- Add strategies for Gradle Plugin Portal, Go Modules, Crates.io, RubyGems as needed
- For any registry not yet coded: use `CustomHTTPScraper` with Admin-configured URL (already available in MVP)
- Admin can onboard any new library from any ecosystem via the UI Management page + Scraper Config
- No code changes required for custom registries — only DB row + URL configuration

Deliverable: All organizational library ecosystems covered under one dashboard.

---

## 15. Code Quality & Optimization

### 15.1 Async-First

All I/O (DB queries, HTTP calls, email sending) uses `async/await`. Uvicorn runs with `--workers 2` per service. No blocking I/O in request handlers.

### 15.2 Connection Pooling

SQLAlchemy async engine configured with:
```python
engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=10, echo=False)
```

### 15.3 Batch Processing

Scraper, comparison, and recommendation services all support batch endpoints. The scheduler always calls batch endpoints — never loops over single-item calls.

### 15.4 Dependency Injection (FastAPI)

All repository and service objects injected via FastAPI `Depends()`. Never instantiated inside request handlers. Enables easy mocking in tests.

```python
async def get_library_repo(session: AsyncSession = Depends(get_db)) -> LibraryRepository:
    return SQLiteLibraryRepository(session)

@router.get("/libraries")
async def list_libraries(repo: LibraryRepository = Depends(get_library_repo)):
    return await repo.get_all()
```

### 15.5 Pydantic v2 Performance

Use `model_config = ConfigDict(from_attributes=True)` for ORM model conversion. Use `model_validate` instead of `parse_obj`. Avoid re-validating already-validated models.

### 15.6 Code Style

- `ruff` for linting and formatting (replaces flake8 + black + isort)
- `mypy` in strict mode for type safety
- All functions typed with return types
- No `Any` types except at system boundaries (external JSON responses)
- Max function length: 30 lines (split into helpers if longer)

---

---

## 16. Streamlit UI — Dashboard & Management

### 16.1 Technology Choice

Streamlit is chosen for the UI because:
- Pure Python — no JavaScript/HTML needed, consistent with the Python 3.12 stack
- Fast to build interactive data dashboards
- Built-in table, chart, form, and layout components
- Runs as a Docker container on port 8501
- All data fetched from API Gateway — UI contains zero business logic

---

### 16.2 Page: Login

**Access:** Public (unauthenticated)

**Layout:**
```
┌─────────────────────────────────────┐
│     Library Management System       │
│                                     │
│  Username: [________________]       │
│  Password: [________________]       │
│                                     │
│            [ Login ]                │
│                                     │
│  ⚠  Invalid credentials (if error)  │
└─────────────────────────────────────┘
```

**Behaviour:**
- Calls `POST /auth/token` on API Gateway
- On success: stores JWT + role + username in `st.session_state`
- Redirects to Dashboard
- All other pages redirect to Login if session not authenticated

---

### 16.3 Page: Dashboard (Admin + Viewer)

**Layout:**
```
┌── Sidebar ─────────────────────────────────────────────────────────┐
│  👤 John (Admin)     [ Logout ]                                    │
│  ─────────────────────────────                                     │
│  📊 Dashboard                                                      │
│  🔍 Library Detail                                                 │
│  ⚙️  Management          [Admin only]                              │
│  🕐 Scheduler Config     [Admin only]                              │
│  📧 Notifications Config [Admin only]                              │
│  👥 User Management      [Admin only]                              │
└────────────────────────────────────────────────────────────────────┘

┌── Main Content ─────────────────────────────────────────────────────┐
│                                                                      │
│  [ 119 Total ] [ 61 Need Update ] [ 8 Deprecated ] [ 95 Active ]    │
│                                                                      │
│  Filters:  Platform [All ▼]  Status [All ▼]  Update [All ▼]  [🔍]  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ # │ Library         │ Platform │ Current  │ Latest  │ Update │   │
│  │───┼─────────────────┼──────────┼──────────┼─────────┼────────│   │
│  │ 1 │ adobe:sdk-bom   │ Android  │ 3.6.0    │ 3.18.0  │🔴 MAND │   │
│  │ 2 │ constraintlayout│ Android  │ 2.2.1    │ 2.2.1   │✅ OK   │   │
│  │ 3 │ lifecycle-view  │ Android  │ 2.8.7    │ 2.10.0  │🟡 RECD │   │
│  │...│                 │          │          │         │        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Status Distribution:  [Pie Chart]  │  Last Pipeline Run: 2026-06-25│
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Color coding:**
- 🔴 Red row — `update_needed = Mandatory` or `status = Deprecated`
- 🟡 Yellow row — `update_needed = Recommended`
- ✅ Green row — `update_needed = None` / in sync

**Filters:** Platform (Android/iOS/All) · Status (Active/Deprecated/Legacy/All) · Update Needed (Mandatory/Recommended/None/All)

**Clickable rows** → navigate to Library Detail page

---

### 16.4 Page: Library Detail (Admin + Viewer)

**Layout:**
```
  Library: com.adobe.marketing.mobile:sdk-bom
  ─────────────────────────────────────────────
  Platform: Android       Registry: Maven Central
  Status:   🟢 Active     Priority: PI 31

  ┌─ Versions ──────────────────────────────┐
  │ Current (in repo): 3.6.0                │
  │ Latest  (scraped): 3.18.0               │
  │ New version available: ✅ YES           │
  │ Last checked: 2026-06-25                │
  └──────────────────────────────────────── ┘

  ┌─ Recommendation ────────────────────────┐
  │ Decision: UPGRADE RECOMMENDED           │
  │ Summary: Major version upgrade...       │
  │                                         │
  │ ✅ Pros (Upgrade):                      │
  │   • Security patches included           │
  │   • New BOM consolidates all versions   │
  │ ❌ Cons (Upgrade):                      │
  │   • Major version — check release notes │
  │                                         │
  │ ✅ Pros (Stay):                         │
  │   • No immediate disruption             │
  │ ❌ Cons (Stay):                         │
  │   • Missing security updates            │
  │   • Out of sync with PI 31 mandate      │
  └──────────────────────────────────────── ┘

  ┌─ Version History ───────────────────────┐
  │ Date       │ Version │ Type    │ Source  │
  │ 2026-06-25 │ 3.6.0   │ current │ PDF     │
  │ 2026-06-25 │ 3.18.0  │ latest  │ scraper │
  └──────────────────────────────────────── ┘

  ┌─ Update History (Admin audit log) ──────┐
  │ Date       │ By     │ Field    │ Reason  │
  │ 2026-06-25 │ admin  │ imported │ PDF load│
  └──────────────────────────────────────── ┘

  ┌─ External Links ────────────────────────┐
  │ 🔗 mvnrepository.com/...  [Open]        │
  │ 🔗 Release Notes [added by admin] [Open]│
  └──────────────────────────────────────── ┘
```

---

### 16.5 Page: Management — Admin Only

**Capabilities:**

```
  Select Library: [com.adobe.marketing.mobile:sdk-bom ▼]

  ┌─ Edit Library Info ─────────────────────────────────┐
  │ Current Version:  [3.6.0          ]                 │
  │ Status:           [Active ▼       ]                 │
  │ Update Needed:    [Mandatory ▼    ]                 │
  │ Priority:         [PI 31          ]                 │
  │ Comments:         [________________]                │
  │                                                     │
  │ Reason for update: [____________________________]   │
  │                    (saved to library_update_log)    │
  │                                                     │
  │ [ Save Changes ]                                    │
  └──────────────────────────────────────────────────── ┘

  ┌─ Add External URL ──────────────────────────────────┐
  │ Source Name:  [Release Notes Page    ]              │
  │ URL:          [https://...           ]              │
  │ Source Type:  [release_notes ▼       ]              │
  │ [ Add URL ]                                         │
  │                                                     │
  │ Existing URLs:                                      │
  │  • mvnrepository.com/... (registry) [Remove]        │
  │  • github.com/.../releases (release_notes) [Remove] │
  └──────────────────────────────────────────────────── ┘
```

**Every save action writes to `library_update_log`:** timestamp, username, field changed, old value, new value, reason.

---

### 16.6 Page: Scheduler Config — Admin Only

```
  ┌─ Schedule Configuration ────────────────────────────┐
  │ Current Schedule:  0 8 * * 1  (Mon 8:00 AM)        │
  │ Status:            🟢 Enabled                       │
  │                                                     │
  │ Cron Expression:   [0 8 * * 1     ]  [Validate]    │
  │ Human readable:    "Every Monday at 08:00"          │
  │                                                     │
  │ Channels:  ☑ Email   ☑ Teams                       │
  │                                                     │
  │ [ Save Schedule ]   [ Disable ]                     │
  └──────────────────────────────────────────────────── ┘

  ┌─ Manual Run ────────────────────────────────────────┐
  │ [ ▶ Trigger Pipeline Now ]                          │
  │                                                     │
  │ Last Run: 2026-06-25 08:02:14  ✅ completed         │
  │ Libraries: 119 processed / 0 errors                 │
  └──────────────────────────────────────────────────── ┘

  ┌─ Run History ───────────────────────────────────────┐
  │ Run ID   │ Triggered │ Status    │ Libs │ Errors │  │
  │ a1b2...  │ scheduler │ completed │ 119  │ 0      │  │
  │ c3d4...  │ manual    │ partial   │ 117  │ 2      │  │
  └──────────────────────────────────────────────────── ┘
```

---

### 16.7 Page: Notifications Config — Admin Only

```
  ┌─ Email Configuration ───────────────────────────────┐
  │ Enabled:   ☑                                        │
  │ Recipients: team@org.com, dev@org.com               │
  │             [ + Add recipient ]                     │
  │ [ Send Test Email ]                                 │
  └──────────────────────────────────────────────────── ┘

  ┌─ Microsoft Teams Configuration ────────────────────┐
  │ Enabled:      ☑                                    │
  │ Webhook URL:  [https://outlook.office.com/webhook/ ]│
  │               [Test] [Save]                        │
  └──────────────────────────────────────────────────── ┘
```

---

### 16.8 Page: LLM Configuration — Admin Only

```
  ┌─ LLM Provider ─────────────────────────────────────────────────────┐
  │ Provider:    [OpenAI ▼]  (OpenAI / Azure OpenAI / Anthropic / Ollama)│
  │ Model:       [gpt-4o ▼]  (auto-populated based on provider)        │
  │ API Key:     [●●●●●●●●●●●●●●●●●●●●]  [Show] [Clear]              │
  │ API Base URL:[https://api.openai.com/v1  ] ← required for Azure/Ollama│
  │ API Version: [2024-02-01    ] ← required for Azure OpenAI only     │
  │ Temperature: [0.3  ] (0.0 = deterministic, 1.0 = creative)         │
  │ Max Tokens:  [1024 ]                                                │
  │ Timeout (s): [30   ]                                                │
  │ Enabled:     ☑                                                      │
  │                                                                     │
  │ [ Save LLM Config ]   [ Test Connection ]                           │
  │                                                                     │
  │ Last test:  ✅ 2026-06-25 08:00  gpt-4o responded in 1.2s          │
  └──────────────────────────────────────────────────────────────────── ┘

  ┌─ Prompt Templates Editor ──────────────────────────────────────────┐
  │                                                                     │
  │ Select Prompt: [system_prompt ▼]                                    │
  │                                                                     │
  │ Available variables:  {package} {platform} {current_version}       │
  │                       {latest_version} {release_notes}             │
  │                       {deprecation_notes} {update_needed}          │
  │                                                                     │
  │ Template Text:                                                      │
  │ ┌─────────────────────────────────────────────────────────────┐   │
  │ │ You are a software library upgrade advisor for an           │   │
  │ │ enterprise mobile development team. Analyze the library     │   │
  │ │ upgrade scenario and provide structured JSON output with    │   │
  │ │ upgrade_pros, upgrade_cons, no_upgrade_pros, no_upgrade_    │   │
  │ │ cons, and recommendation_summary fields.                    │   │
  │ └─────────────────────────────────────────────────────────────┘   │
  │                                                                     │
  │ [ Save Prompt ]  [ Reset to Default ]  [ Preview with Sample ]     │
  │                                                                     │
  │ ── All Prompts ────────────────────────────────────────────────    │
  │  Key                   Version  Updated By  Updated At             │
  │  system_prompt           v3      admin       2026-06-25            │
  │  upgrade_pros            v2      admin       2026-06-24            │
  │  upgrade_cons            v2      admin       2026-06-24            │
  │  no_upgrade_pros         v1      admin       2026-06-23            │
  │  no_upgrade_cons         v1      admin       2026-06-23            │
  │  recommendation_summary  v2      admin       2026-06-24            │
  │  email_subject           v1      admin       2026-06-23            │
  │  email_intro             v1      admin       2026-06-23            │
  │  teams_title             v1      admin       2026-06-23            │
  └──────────────────────────────────────────────────────────────────── ┘
```

**Behaviour:**
- API key saved encrypted (AES-256) into `llm_config.api_key_encrypted`
- "Test Connection" calls `POST /recommendations/test-llm` — sends a sample library payload and shows LLM response in UI
- "Preview with Sample" renders the prompt with fixture data so Admin can validate before saving
- If LLM disabled → recommendation-service falls back to rule-based generators automatically

---

### 16.9 Page: Scraper Configuration — Admin Only

```
  ┌─ Registry Configuration ───────────────────────────────────────────┐
  │ Select Registry: [maven ▼]  (maven / cocoapods / spm / github / custom)│
  │                                                                     │
  │ Base URL:        [https://search.maven.org/solrsearch/select ]      │
  │ Timeout (s):     [10  ]                                             │
  │ Rate Limit/min:  [60  ]                                             │
  │ Max Retries:     [3   ]                                             │
  │ CB Threshold:    [5   ] ← circuit breaker failure threshold         │
  │ CB Cooldown (s): [60  ] ← seconds before retrying after CB opens   │
  │ Custom Headers:  [{}  ] ← JSON object (e.g. auth headers)          │
  │ Enabled:         ☑                                                  │
  │                                                                     │
  │ [ Save Registry Config ]   [ Test Registry ]                        │
  └──────────────────────────────────────────────────────────────────── ┘

  ┌─ All Registry Status ──────────────────────────────────────────────┐
  │ Registry   │ Status  │ Timeout │ Rate Lim │ CB Threshold │ Enabled │
  │ maven      │ 🟢 OK   │ 10s     │ 60/min   │ 5            │ ☑       │
  │ cocoapods  │ 🟢 OK   │ 10s     │ 30/min   │ 5            │ ☑       │
  │ spm        │ 🟡 SLOW │ 10s     │ 30/min   │ 5            │ ☑       │
  │ github     │ 🟢 OK   │ 15s     │ 60/min   │ 3            │ ☑       │
  │ custom     │ —       │ 10s     │ 30/min   │ 5            │ ☑       │
  └──────────────────────────────────────────────────────────────────── ┘

  ┌─ Library → Registry Mapping ───────────────────────────────────────┐
  │ Shows each library and which scraper strategy it uses              │
  │                                                                     │
  │ Library                        │ Registry  │ Override URL          │
  │ com.adobe.marketing.mobile:*   │ maven     │ —                     │
  │ AEPCore                        │ cocoapods │ —                     │
  │ ACI-OPPWAMobile                │ custom    │ https://aciworldwide/ │
  │                                                                     │
  │ [Edit Mapping]                                                      │
  └──────────────────────────────────────────────────────────────────── ┘
```

---

### 16.10 Page: System Health — Admin + Viewer

```
  ┌─ Service Health ───────────────────────────────────────────────────┐
  │ Service               │ Status    │ Version │ Last Checked          │
  │ api-gateway    :8000  │ 🟢 Healthy│ 1.0.0   │ 2026-06-25 08:05:01  │
  │ library-data   :8001  │ 🟢 Healthy│ 1.0.0   │ 2026-06-25 08:05:01  │
  │ scraper        :8002  │ 🟢 Healthy│ 1.0.0   │ 2026-06-25 08:05:01  │
  │ comparison     :8003  │ 🟢 Healthy│ 1.0.0   │ 2026-06-25 08:05:01  │
  │ recommendation :8004  │ 🟢 Healthy│ 1.0.0   │ 2026-06-25 08:05:01  │
  │ notification   :8005  │ 🟡 Degraded│ 1.0.0  │ 2026-06-25 08:05:01  │
  │ scheduler      :8006  │ 🟢 Healthy│ 1.0.0   │ 2026-06-25 08:05:01  │
  │                                                                     │
  │ [ Refresh Status ]                                                  │
  └──────────────────────────────────────────────────────────────────── ┘

  ┌─ Database Stats ───────────────────────────────────────────────────┐
  │ Total Libraries:       119  (Android: 74 / iOS: 45)                │
  │ Mandatory Updates:      61  (Android: 28 / iOS: 33)                │
  │ Deprecated:              8  (Android: 6  / iOS: 2)                 │
  │ Recommendations in DB:   0  (not yet generated)                    │
  │ Last Scrape Run:  2026-06-25 08:02:14  ✅ 119/119 succeeded        │
  │ DB File Size:     2.4 MB                                           │
  └──────────────────────────────────────────────────────────────────── ┘

  ┌─ LLM Status ──────────────────────────────────────────────────────┐
  │ Provider:  OpenAI       Model: gpt-4o     Enabled: ✅              │
  │ Last test: 2026-06-25   Status: ✅ Connected                       │
  └──────────────────────────────────────────────────────────────────── ┘

  ┌─ Pipeline Last Run ────────────────────────────────────────────────┐
  │ Run ID: a1b2c3d4   Triggered: scheduler   Status: ✅ completed     │
  │ Started: 08:00:00  Finished: 08:02:14     Duration: 2m 14s        │
  │ Libraries: 119 processed / 119 scraped / 119 compared / 0 errors  │
  └──────────────────────────────────────────────────────────────────── ┘
```

---

### 16.11 Page: User Management — Admin Only

```
  ┌─ Users ─────────────────────────────────────────────┐
  │ Username  │ Full Name   │ Role   │ Active │ Actions  │
  │ admin     │ Admin User  │ admin  │ ✅     │ Edit     │
  │ jsmith    │ Jane Smith  │ viewer │ ✅     │ Edit│Del │
  └──────────────────────────────────────────────────── ┘

  ┌─ Add User ──────────────────────────────────────────┐
  │ Username:  [________]  Full Name: [_______________] │
  │ Email:     [________________________________]       │
  │ Role:      [viewer ▼]                               │
  │ Password:  [________]  Confirm: [________________]  │
  │ [ Add User ]                                        │
  └──────────────────────────────────────────────────── ┘
```

---

## 17. Persona-Based Access Control

### 17.1 Personas

| Persona | Role | Who | Access Level |
|---------|------|-----|-------------|
| **Admin** | `admin` | Library management team, DevOps lead | Full read + write + configure |
| **Viewer** | `viewer` | App team leads, stakeholders, developers | Read-only dashboard + detail view |

### 17.2 Access Matrix — UI Pages

| Page | Admin | Viewer | Notes |
|------|:-----:|:------:|-------|
| Login | ✓ | ✓ | Public |
| Dashboard | ✓ | ✓ | All libraries, filters, metrics |
| Library Detail | ✓ | ✓ | Versions, recommendation, update log, external links |
| System Health | ✓ | ✓ | Service health, DB stats, LLM status, last pipeline run |
| Management | ✓ | ✗ | Edit library fields, add URLs, set update reason |
| Scheduler Config | ✓ | ✗ | Cron, enable/disable, manual run, run history |
| Notifications Config | ✓ | ✗ | Email + Teams config and test |
| LLM Configuration | ✓ | ✗ | Provider, API key, model, temperature, prompt editor |
| Scraper Configuration | ✓ | ✗ | Registry URLs, timeouts, rate limits, library mapping |
| User Management | ✓ | ✗ | Add/edit/deactivate users + roles |

### 17.3 Access Matrix — API Endpoints

| HTTP Method | Endpoint Pattern | Admin | Viewer |
|-------------|-----------------|:-----:|:------:|
| GET | `/libraries*` | ✓ | ✓ |
| GET | `/recommendations*` | ✓ | ✓ |
| GET | `/version-history*` | ✓ | ✓ |
| GET | `/notifications*` | ✓ | ✓ |
| GET | `/schedule*` | ✓ | ✓ |
| GET | `/runs*` | ✓ | ✓ |
| GET | `/health*` | ✓ | ✓ |
| GET | `/llm-config` | ✓ | ✓ (masked — no key returned) |
| GET | `/scraper-config*` | ✓ | ✓ |
| GET | `/app-settings` | ✓ | ✓ (sensitive values masked) |
| PUT/POST | `/libraries*` | ✓ | ✗ |
| POST | `/library-external-sources` | ✓ | ✗ |
| PUT | `/schedule` | ✓ | ✗ |
| POST | `/run/now` | ✓ | ✗ |
| PUT/POST/DELETE | `/notifications/config` | ✓ | ✗ |
| POST | `/notify/*` | ✓ | ✗ |
| PUT | `/llm-config` | ✓ | ✗ |
| POST | `/llm-prompts` | ✓ | ✗ |
| PUT | `/llm-prompts/{key}` | ✓ | ✗ |
| POST | `/recommendations/test-llm` | ✓ | ✗ |
| PUT/POST | `/scraper-config*` | ✓ | ✗ |
| PUT/POST | `/app-settings` | ✓ | ✗ |
| GET/POST/PUT/DELETE | `/users*` | ✓ | ✗ |

### 17.4 Session Security

- JWT stored in `st.session_state` (server-side Streamlit memory — not exposed to browser localStorage)
- Session expires when browser tab closes or JWT expires
- No concurrent session tracking needed for v1 (org-internal tool)
- Password change forced on first Admin login
- Viewer accounts created by Admin only — no self-registration

### 17.5 Viewer Experience

Viewers see the full Dashboard and Library Detail pages. Admin-only pages are hidden from the sidebar entirely (not just greyed out). If a Viewer attempts a direct URL to an Admin page, they are silently redirected to the Dashboard.

---

## 19. Business Gaps & Enhancements

> These items are identified as missing from the current business design. They do not change the MVP scope (Days 1–5) but must be addressed before or during the relevant development phase.

---

### B1 — Upgrade Lifecycle Tracking

**Gap:** The system generates recommendations but has no way to track whether anyone acted on them. The same library will be flagged as "Mandatory" every single pipeline run indefinitely, causing notification fatigue.

**Solution:** Add an upgrade lifecycle with the following states:

```
Pending → Acknowledged → Scheduled → In Progress → Completed
                                                  ↘ Skipped (with reason)
```

**DB Table:**
```sql
CREATE TABLE upgrade_lifecycle (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id      INTEGER NOT NULL REFERENCES libraries(id),
    recommendation_id INTEGER REFERENCES recommendations(id),
    status          TEXT NOT NULL DEFAULT 'Pending'
                    CHECK(status IN ('Pending','Acknowledged','Scheduled',
                                     'In Progress','Completed','Skipped')),
    target_version  TEXT,                    -- version being upgraded to
    target_sprint   TEXT,                    -- e.g. "PI 31 Sprint 2"
    target_date     TEXT,                    -- planned completion date
    completed_version TEXT,                  -- actual version after upgrade
    skip_reason     TEXT,                    -- reason if Skipped
    actioned_by     TEXT,                    -- username
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
```

**UI Impact:**
- Library Detail page: shows current lifecycle status with action buttons [Acknowledge] [Schedule] [Mark Complete] [Skip]
- Dashboard: new column "Lifecycle" with colour-coded badge
- Dashboard filter: filter by lifecycle status
- Notification service: skip sending notification for libraries in "Completed" or "Skipped" lifecycle states

---

### B2 — Notification Deduplication / Change-Only Alerts

**Gap:** Every scheduled run sends a full notification regardless of whether anything changed. Stakeholders receive identical emails weekly — notification fatigue leads to them being ignored.

**Solution:** Track what was last notified per library. Only include a library in a notification if its state changed since the last notification.

**DB Table:**
```sql
CREATE TABLE notification_sent_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id      INTEGER NOT NULL REFERENCES libraries(id),
    notification_id INTEGER REFERENCES notifications(id),
    latest_version_at_send TEXT,            -- latest version when notification sent
    update_needed_at_send  TEXT,            -- update_needed value when sent
    status_at_send         TEXT,            -- status when sent
    content_hash    TEXT NOT NULL,          -- SHA-256 of notification content
    sent_at         TEXT DEFAULT (datetime('now'))
);
```

**Logic in notification-service:**
```
For each library:
  current_hash = SHA-256(latest_version + update_needed + status)
  last_hash = SELECT content_hash FROM notification_sent_log
              WHERE library_id = ? ORDER BY sent_at DESC LIMIT 1
  IF current_hash != last_hash → include in notification
  ELSE → skip (nothing changed)
```

**Critical Alert Override:** Libraries with `priority = 'Critical'` or `deadline_date` within 14 days are always included regardless of hash.

---

### B3 — Bulk Library Import

**Gap:** New libraries can only be added one at a time via the Management UI. Teams need to onboard hundreds of libraries at once from existing project files.

**Supported import formats:**

| Format | Framework | Parsed From |
|--------|-----------|-------------|
| `requirements.txt` | Python (PyPI) | package==version lines |
| `pom.xml` | Java/Android (Maven) | `<dependency>` blocks |
| `build.gradle` / `build.gradle.kts` | Android (Maven) | `implementation "..."` lines |
| `Podfile` | iOS (CocoaPods) | `pod 'Name', 'version'` lines |
| `Package.swift` | iOS (SPM) | `.package(url:..., from:...)` |
| `package.json` | Web (npm) | `dependencies` + `devDependencies` |
| CSV/Excel | Any | Columns: package, sdk_name, platform, registry, current_version |

**DB Table:**
```sql
CREATE TABLE bulk_import_job (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL UNIQUE,    -- UUID
    import_format   TEXT NOT NULL,           -- 'requirements_txt'|'pom_xml'|'podfile'|'csv'|...
    filename        TEXT NOT NULL,
    total_rows      INTEGER DEFAULT 0,
    imported        INTEGER DEFAULT 0,
    skipped         INTEGER DEFAULT 0,       -- already exists in DB
    failed          INTEGER DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'processing'
                    CHECK(status IN ('processing','completed','failed')),
    error_log       TEXT,                    -- JSON array of row errors
    imported_by     TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    finished_at     TEXT
);
```

**UI:** Management page → new tab "Bulk Import" → file upload → parse preview → confirm → import → progress bar.

---

### B4 — Library Ownership / Team Assignment

**Gap:** No concept of which application team owns which library. All notifications go to all recipients — no targeted accountability.

**Solution:** Each library can be assigned to one or more application teams. Notifications can optionally be targeted.

**DB Table:**
```sql
CREATE TABLE application_teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name   TEXT NOT NULL UNIQUE,
    team_email  TEXT,                        -- team distribution list
    teams_channel TEXT,                      -- Teams channel webhook (optional)
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE library_ownership (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id      INTEGER NOT NULL REFERENCES libraries(id),
    team_id         INTEGER NOT NULL REFERENCES application_teams(id),
    is_primary      INTEGER NOT NULL DEFAULT 1,  -- 1 = primary owner
    assigned_by     TEXT NOT NULL,
    assigned_at     TEXT DEFAULT (datetime('now')),
    UNIQUE(library_id, team_id)
);
```

**UI:** Management page → "Assign Team" section per library.
**Notification:** If team has its own email/webhook → send targeted notification to owning team in addition to global notification.

---

### B5 — Data Retention Policy

**Gap:** `version_history`, `scrape_log`, `pipeline_run_details`, `notification_sent_log`, and `library_update_log` will grow unboundedly with no cleanup.

**Solution:** Add retention configuration to `app_settings` and a cleanup job in the scheduler.

**New `app_settings` rows:**
```
('retention_version_history_days',     '365',  'Keep version history for N days', 0)
('retention_scrape_log_days',          '90',   'Keep scrape log entries for N days', 0)
('retention_pipeline_run_days',        '180',  'Keep pipeline run details for N days', 0)
('retention_notification_log_days',    '365',  'Keep notification sent log for N days', 0)
('retention_library_update_log_days',  '730',  'Keep audit log for N days (compliance)', 0)
```

**Cleanup step** added to scheduler pipeline after notification step:
```python
class CleanupStep(PipelineStep):
    """Deletes records older than retention thresholds."""
    async def handle(self, context: PipelineContext) -> PipelineContext: ...
```

**UI:** Scheduler Config page → "Data Retention" section with editable thresholds.

---

### B6 — Export / Reporting for Management

**Gap:** Viewer persona has no way to extract data. Management needs exportable reports.

**Solution:**
- Dashboard: "Export CSV" button (both personas) → downloads filtered library table as CSV
- Dashboard: "Export Excel" button → formatted Excel with status colour coding
- Library Detail: no export needed (view-only)
- Admin: "Full Report" → generates a summary PDF/HTML snapshot for management distribution

**New endpoint in library-data-service:**
```
GET /libraries/export?format=csv&platform=Android&update_needed=Mandatory
GET /libraries/export?format=excel
```

**No new DB tables needed** — export is a read operation on existing data.

---

### B7 — Critical / Urgent Alert Mechanism

**Gap:** The ACI-OPPWAMobile Mastercard certificate expires **15 July 2026** (critical hard deadline). The current system treats this as just another "Mandatory" library. No mechanism exists for:
- Deadline-based escalation
- Immediate alert (not waiting for next scheduled run)
- Priority classification beyond Mandatory/Recommended

**Solution:** Add `priority` and `deadline_date` to the `libraries` table (via Alembic migration):

```sql
-- Add to existing libraries table
ALTER TABLE libraries ADD COLUMN alert_priority TEXT DEFAULT 'Normal'
    CHECK(alert_priority IN ('Normal','High','Critical'));
ALTER TABLE libraries ADD COLUMN deadline_date TEXT;   -- ISO date, e.g. "2026-07-15"
ALTER TABLE libraries ADD COLUMN deadline_notes TEXT;  -- e.g. "Mastercard cert expiry"
```

**Logic:**
- `Critical` + `deadline_date` within 14 days → immediate notification triggered on every pipeline run
- `Critical` libraries highlighted with ⚠️ banner on Dashboard and in emails
- Admin can set `alert_priority` and `deadline_date` via Management UI

**Pre-seed for ACI-OPPWAMobile:**
```sql
UPDATE libraries SET alert_priority='Critical',
    deadline_date='2026-07-15',
    deadline_notes='Mastercard certificate expiry. Must upgrade to mSDK 7.11.0 + IPWorks 2.4.9625 by 7 July 2026.'
WHERE package LIKE '%OPPWA%' OR package LIKE '%ipworks%';
```

---

### B8 — Non-Semver Version Edge Cases (Business Impact)

**Gap:** Several libraries in the existing DB have non-standard versions that will produce no useful recommendation without a fallback strategy:

| Library | Current Version | Issue |
|---------|----------------|-------|
| Gigya (Android) | `core-v7.1.7` | Prefix breaks semver parse |
| OneTrust | `202407.1.0.0` | Date-based versioning |
| OTPublishersHeadlessSDK | `NotinPodfile.lock` | Placeholder text |
| AppsFlyer | `ViaSPM` | Source indicator, not version |
| IovationCustomSDK, EncryptedCoreData, SQLCipher (iOS) | `55.0(internal)` | Internal version tag |

**Business Rule:**
- `ViaSPM`, `NotinPodfile.lock`, `55.0(internal)` → mark `current_version_status = 'unknown'` → skip comparison → UI shows "Version not tracked — enter manually"
- `202407.1.0.0` → treat as `YYYYMM.major.minor.patch` → compare numerically
- `core-v7.1.7` → strip prefix with regex `[0-9]+\.[0-9]+\.[0-9]+` → parse normally

**No structural change needed** — handled in comparison-service `comparison.py` pre-processing step.

---

## 20. Technical Gaps & Hardening

> These items strengthen the technical foundation. Items marked 🔴 must be addressed during MVP (Days 1–5). Items marked 🟡 are addressed in hardening pass (Day 5 or v2).

---

### T1 — Scraper Result Caching 🔴

**Gap:** Every pipeline run hits all external registries fresh. Maven Central, GitHub API (5000 req/hr with token), and CocoaPods all have rate limits. 119+ libraries × daily runs = unsustainable without caching.

**Solution:** Cache scrape results with a configurable TTL. Re-use cached result if not expired.

**DB Table:**
```sql
CREATE TABLE scrape_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id      INTEGER NOT NULL REFERENCES libraries(id),
    registry_key    TEXT NOT NULL,
    scraped_version TEXT NOT NULL,
    release_notes   TEXT,
    raw_response    TEXT,                    -- JSON of full registry response
    expires_at      TEXT NOT NULL,           -- datetime: scraped_at + TTL
    scraped_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(library_id, registry_key)         -- one cache entry per library per registry
);
```

**Logic in scraper-service:**
```python
cache = await cache_repo.get(library_id, registry_key)
if cache and cache.expires_at > now():
    return CachedResult(cache)              # skip external call
result = await strategy.fetch(package)
await cache_repo.upsert(library_id, registry_key, result, ttl_hours=6)
```

**`app_settings` key:** `scraper_cache_ttl_hours` (default: `6`)
**UI:** Scraper Config page → "Cache TTL (hours)" field.

---

### T2 — Concurrent Pipeline Run Protection 🔴

**Gap:** If Admin triggers "Run Now" while the APScheduler fires simultaneously, two pipeline instances run in parallel → duplicate DB writes, duplicate notifications sent.

**Solution:** Check for active run before starting. Reject if already running.

```python
# In scheduler.py, before starting pipeline:
active = await pipeline_run_repo.get_active()
if active:
    logger.warning("pipeline_already_running", run_id=active.run_id)
    return {"error": "Pipeline already running", "run_id": active.run_id}

# On startup: heal stale 'running' rows older than 30 minutes
await pipeline_run_repo.mark_stale_as_failed(threshold_minutes=30)
```

**No new DB table needed** — uses existing `pipeline_runs.status` column.

---

### T3 — API Versioning 🔴

**Gap:** All endpoints (`/libraries`, `/scrape`, etc.) have no version prefix. When contracts change, there is no backward compatibility path.

**Solution:** All routers prefixed with `/api/v1/` from day one.

```python
# In each service main.py
app.include_router(libraries_router, prefix="/api/v1")
app.include_router(health_router)          # /health stays unversioned
```

**API Gateway proxy routes:**
```
/api/v1/libraries*     → library-data-service:8001/api/v1/libraries*
/api/v1/scrape*        → scraper-service:8002/api/v1/scrape*
```

**No DB change needed.**

---

### T4 — Non-Semver Version Handling 🔴

**Gap:** `packaging.version.parse()` raises `InvalidVersion` for versions like `core-v7.1.7`, `202407.1.0.0`, `ViaSPM`, `NotinPodfile.lock`, `55.0(internal)`. This will crash batch comparisons.

**Solution:** Add pre-processing in comparison-service `comparison.py`:

```python
import re
from packaging.version import Version, InvalidVersion

def normalise_version(raw: str) -> tuple[Version | None, str]:
    """
    Returns (parsed_version, strategy_used).
    strategy_used: 'semver' | 'extracted' | 'date_based' | 'unknown'
    """
    raw = raw.strip()
    if not raw or raw.lower() in ('viaspm','notinpodfile.lock','n/a','unknown','—'):
        return None, 'unknown'
    # Try direct parse
    try:
        return Version(raw), 'semver'
    except InvalidVersion:
        pass
    # Try extracting numeric part (e.g. "core-v7.1.7" → "7.1.7")
    match = re.search(r'(\d+\.\d+[\.\d]*)', raw)
    if match:
        try:
            return Version(match.group(1)), 'extracted'
        except InvalidVersion:
            pass
    return None, 'unknown'
```

**If both versions return `None`** → `new_version_released = None` → comparison flagged as `'manual_review'` → shown in Dashboard with "⚠️ Manual Review" badge.

---

### T5 — LLM Token / Cost Tracking 🟡

**Gap:** No visibility into how many LLM API tokens are consumed per run or monthly cost. With GPT-4o at ~$5/1M tokens, 119 libraries × daily runs = measurable cost.

**DB Table:**
```sql
CREATE TABLE llm_usage_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT REFERENCES pipeline_runs(run_id),
    library_id      INTEGER REFERENCES libraries(id),
    prompt_key      TEXT,                    -- which prompt template was used
    model           TEXT NOT NULL,
    prompt_tokens   INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,    -- calculated at log time
    latency_ms      INTEGER,
    logged_at       TEXT DEFAULT (datetime('now'))
);
```

**UI:** System Health page → "LLM Usage" section:
- Tokens used this run / this month
- Estimated cost this run / this month
- Average latency per call

---

### T6 — Database Backup Strategy 🔴

**Gap:** SQLite is a single file on a Docker volume. No backup strategy exists. A container crash mid-write or disk failure loses all data.

**Solution:** Add a backup step to the scheduler pipeline (runs after CleanupStep).

```python
class BackupDatabaseStep(PipelineStep):
    """Copies library_management.db to a timestamped backup file."""
    async def handle(self, context: PipelineContext) -> PipelineContext:
        src  = Path("/app/db/library_management.db")
        dest = Path(f"/app/db/backups/backup_{datetime.now():%Y%m%d_%H%M%S}.db")
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(src, dest)
        # Prune: keep last N backups (configurable)
        self._prune_old_backups(dest.parent, keep=7)
        return context
```

**Docker Compose volume:**
```yaml
library-data-service:
  volumes:
    - ./db:/app/db:rw          # existing
    - ./db/backups:/app/db/backups:rw   # backup destination
```

**`app_settings` key:** `db_backup_keep_count` (default: `7`)
**UI:** Scheduler Config page → "Database Backup" section: last backup date, backup count, manual trigger.

---

### T7 — Cron Timezone Configuration 🟡

**Gap:** `0 8 * * 1` fires at 08:00 UTC. If the organisation is in IST (+5:30), that is 13:30 IST — not Monday morning. If in AEST (+10), that is 18:00 Sunday.

**Solution:** Add timezone setting to `app_settings` and pass to APScheduler.

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo

scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.schedule_timezone))
```

**`app_settings` key:** `schedule_timezone` (default: `"UTC"`)
**UI:** Scheduler Config page → "Timezone" dropdown (pytz timezone list).
**Human-readable display:** "Every Monday at 08:00 IST" shown below the cron expression.

---

### T8 — Release Notes HTML / Markdown Parsing 🟡

**Gap:** Registry release notes are returned as raw HTML or Markdown. Feeding `<p>`, `<ul>`, `<li>` tags to the LLM wastes tokens and produces worse output.

**Solution:** Pre-process release notes before LLM prompt construction in `recommendation-service/llm/prompt_builder.py`:

```python
import html
from markdown import markdown
from bs4 import BeautifulSoup

def clean_release_notes(raw: str) -> str:
    """Strip HTML/Markdown → plain text, max 1000 chars for LLM prompt."""
    if not raw:
        return ""
    # Render Markdown → HTML → strip tags
    html_content = markdown(raw)
    text = BeautifulSoup(html_content, "html.parser").get_text(separator=" ")
    text = html.unescape(text)
    return text[:1000].strip()
```

**New dependencies:** `markdown`, `beautifulsoup4` in `recommendation-service/requirements.txt`.

---

### T9 — Docker Image Vulnerability Scanning 🟡

**Gap:** No image scanning step defined. Base image `python:3.12-slim` may carry known CVEs.

**Solution:** Add `trivy` scan to the build process.

```makefile
# In Makefile
scan:
    @for svc in library-data-service scraper-service comparison-service \
                recommendation-service notification-service scheduler-service \
                api-gateway ui-service; do \
        echo "Scanning $$svc..."; \
        trivy image lib-mgmt/$$svc:latest --exit-code 1 --severity HIGH,CRITICAL; \
    done

build-and-scan: build scan
```

**CI pipeline step (GitHub Actions):**
```yaml
- name: Scan Docker images
  run: trivy image --exit-code 1 --severity HIGH,CRITICAL lib-mgmt/${{ matrix.service }}:latest
```

---

### T10 — Graceful Pipeline Shutdown on SIGTERM 🟡

**Gap:** If the scheduler container stops (docker restart, deploy) while a pipeline run is active, the `pipeline_runs.status` row stays stuck as `running` forever. On restart, the startup heal check would mark it `failed` but the current library being processed is lost mid-write.

**Solution:** Catch `SIGTERM` in the scheduler and set a cancellation flag that each pipeline step checks.

```python
import signal, asyncio

shutdown_event = asyncio.Event()

def handle_sigterm(*_):
    shutdown_event.set()

signal.signal(signal.SIGTERM, handle_sigterm)

class PipelineStep(ABC):
    async def handle(self, context: PipelineContext) -> PipelineContext:
        if shutdown_event.is_set():
            context.cancelled = True
            return context              # exit cleanly
        return await self._run(context)
```

**On startup:** mark any `pipeline_runs` with `status='running'` and `started_at` older than 30 minutes as `failed` (stale run heal).

---

### T11 — Audit Log Immutability Enforcement 🟡

**Gap:** The `library_update_log` table is the system's compliance audit trail. It must be **append-only** — no updates or deletes ever. The SQLite schema allows this but nothing enforces it at the application layer.

**Solution:** Repository layer enforcement — the `LibraryUpdateLogRepository` exposes **only** `insert()`. No `update()`, no `delete()` methods exist.

```python
class LibraryUpdateLogRepository:
    async def insert(self, entry: LibraryUpdateLogCreate) -> LibraryUpdateLog:
        ...                              # ONLY method — append only

    # No update(), no delete(), no bulk_delete() methods
    # SQLite trigger as belt-and-suspenders:
```

```sql
-- Belt-and-suspenders: DB-level trigger rejects any UPDATE/DELETE
CREATE TRIGGER audit_log_immutable_update
    BEFORE UPDATE ON library_update_log
BEGIN
    SELECT RAISE(ABORT, 'library_update_log is immutable — no updates allowed');
END;

CREATE TRIGGER audit_log_immutable_delete
    BEFORE DELETE ON library_update_log
BEGIN
    SELECT RAISE(ABORT, 'library_update_log is immutable — no deletes allowed');
END;
```

---

## Appendix — Key Decisions Summary

| Decision | Choice | Reason |
|----------|--------|--------|
| Framework | FastAPI | Async-native, Pydantic integration, auto-generated OpenAPI docs |
| UI | Streamlit | Python-native dashboard, no JS required, fast to build |
| LLM abstraction | litellm | Single interface for OpenAI/Azure/Anthropic/Ollama — switch provider without code changes |
| LLM config storage | `llm_config` DB table | Admin-editable from UI without restart or file edits |
| Prompt storage | `llm_prompt_templates` DB table | Admin can tune prompts live; versioned; no redeploy needed |
| LLM fallback | Rule-based generators | If LLM disabled or API fails — system always produces output |
| API key encryption | AES-256 in DB | Single `DB_ENCRYPTION_KEY` in `.env`; all other secrets UI-managed |
| DB | SQLite | Already in use; sufficient for org-internal tool; no infra overhead |
| ORM | SQLAlchemy 2.x async | Type-safe, async support, Alembic migration compatibility |
| Scraping | HTTPX + Strategy | Async HTTP, registry-specific strategies without coupling |
| Scraper config | `scraper_registry_config` DB table | Admin-tunable timeouts/rate-limits from UI |
| General config | `app_settings` key-value DB table | Single source for all runtime-tunable settings |
| Scheduling | APScheduler | Lightweight, SQLite job store, no external broker needed |
| Email | aiosmtplib | Async SMTP, works with any SMTP provider |
| Teams | Incoming Webhook | Simplest Teams integration, no app registration needed |
| Auth | JWT (HS256) + bcrypt | Stateless tokens, secure password hashing, no external IdP needed |
| Persona | Admin / Viewer roles | Simple two-role model matches org use case |
| External URLs | `library_external_sources` table | Admin-configurable per library, no code changes needed |
| Update Audit | `library_update_log` table | Full traceability of who changed what and why |
| Containerization | Docker Compose | Single host deployment, no Kubernetes overhead for org-internal tool |
| Logging | structlog JSON | Machine-readable, aggregatable, works with any log collector |

---

## Appendix B — Complete UI Configuration Reference

Every configurable item in the system and where to change it:

| Setting | Where | Who | Table / File |
|---------|-------|-----|-------------|
| LLM Provider | UI → LLM Config | Admin | `llm_config` |
| LLM Model | UI → LLM Config | Admin | `llm_config` |
| LLM API Key | UI → LLM Config | Admin | `llm_config.api_key_encrypted` |
| LLM Base URL | UI → LLM Config | Admin | `llm_config` |
| LLM Temperature | UI → LLM Config | Admin | `llm_config` |
| LLM Max Tokens | UI → LLM Config | Admin | `llm_config` |
| LLM Enabled | UI → LLM Config | Admin | `llm_config.enabled` |
| All Prompt Templates | UI → LLM Config | Admin | `llm_prompt_templates` |
| SMTP Host/Port/User/Pass | UI → Notifications Config | Admin | `app_settings` |
| Email Recipients | UI → Notifications Config | Admin | `app_settings.email_recipients` |
| Email Enabled | UI → Notifications Config | Admin | `app_settings.email_enabled` |
| Teams Webhook URL | UI → Notifications Config | Admin | `app_settings.teams_webhook_url` |
| Teams Enabled | UI → Notifications Config | Admin | `app_settings.teams_enabled` |
| Pipeline Cron Schedule | UI → Scheduler Config | Admin | `app_settings.schedule_cron` |
| Schedule Enabled | UI → Scheduler Config | Admin | `app_settings.schedule_enabled` |
| Maven registry URL/timeout | UI → Scraper Config | Admin | `scraper_registry_config` |
| CocoaPods registry URL/timeout | UI → Scraper Config | Admin | `scraper_registry_config` |
| GitHub token | UI → Scraper Config | Admin | `app_settings.github_token_encrypted` |
| Circuit breaker thresholds | UI → Scraper Config | Admin | `scraper_registry_config` |
| Library current version | UI → Management | Admin | `libraries` + `library_update_log` |
| Library status | UI → Management | Admin | `libraries` + `library_update_log` |
| Library external URLs | UI → Management | Admin | `library_external_sources` |
| User accounts / roles | UI → User Management | Admin | `users` |
| New registry onboard (future) | UI → Scraper Config | Admin | `scraper_registry_config` (add row) |

> **Nothing requires a `.env` file edit or container restart after initial deployment.**
> All runtime configuration is stored in the DB and loaded at request time.

---

## 18. Multi-Framework Extensibility Roadmap

### 18.1 Business Case

The organization currently uses libraries across multiple technology stacks beyond Android and iOS. A single library management system covering all ecosystems provides:

| Business Benefit | Description |
|-----------------|-------------|
| Single dashboard | One place to view library health across Android, iOS, Web, Backend, and more |
| Unified notification | One email/Teams update covering all platform library statuses |
| Consistent governance | Same mandatory/recommended/deprecated classification applied org-wide |
| Reduced duplication | One tool maintained instead of per-team solutions |
| Compliance visibility | Security patches across all stacks visible in one place |

### 18.2 Ecosystem Rollout Plan

| Phase | Ecosystem | Language | Registry | Libraries To Cover | Timeline |
|-------|-----------|----------|----------|--------------------|----------|
| **MVP (v1)** | Mobile — Android | Kotlin / Java | Maven Central | 74 (already in DB) | Days 1–5 |
| **MVP (v1)** | Mobile — iOS | Swift / ObjC | CocoaPods + SPM | 45 (already in DB) | Days 1–5 |
| **MVP (v1)** | Vendored / Binary | Any | GitHub Releases + Custom HTTP | ACI, Scandit, IPWorks | Days 1–5 |
| **v2** | Web / Node.js | JavaScript / TypeScript | npm | Frontend + BFF libs | Sprint 6–7 |
| **v2** | Backend | Python | PyPI | Microservice dependencies | Sprint 6–7 |
| **v3** | Enterprise Backend | C# / .NET | NuGet | .NET service libraries | Sprint 8–9 |
| **v3** | Mobile — Flutter | Dart | pub.dev | Cross-platform mobile | Sprint 8–9 |
| **v4** | Build tooling | Groovy / Kotlin DSL | Gradle Plugin Portal | CI/CD plugins | Sprint 10+ |
| **v5+** | Systems / Cloud | Go | Go Module Proxy | Infrastructure tools | Future |
| **v5+** | Systems / Embedded | Rust | Crates.io | Low-level libs | Future |
| **Any time** | Any custom | Any | Admin-configured URL | Internal / private registries | Available now |

### 18.3 Zero-Code Extensibility for Custom Registries

For any registry that does not have a dedicated strategy yet, the **Custom HTTP Scraper** (available in MVP) allows onboarding immediately:

```
Admin UI → Scraper Config → Add Registry
  registry_key:    "internal-nexus"
  display_name:    "Internal Nexus Repository"
  ecosystem:       "backend"
  framework_language: "java"
  base_url:        "https://nexus.org.internal/service/rest/v1/search?name={package}"
  custom_headers:  {"Authorization": "Basic <encoded>"}
  enabled:         true
```
No code change. No redeploy. New registry scraped on next pipeline run.

### 18.4 Adding a Coded Strategy (Developer Steps — v2+)

When a new ecosystem gets a dedicated strategy class for full API compatibility:

```
Step 1: Create  services/scraper-service/src/strategies/npm.py
        class NpmScraper(ScraperStrategy):
            async def fetch(self, package: str) -> ScrapedVersion:
                # call registry.npmjs.org/{package}

Step 2: Register in  factory.py:
        ScraperFactory.register('npm', NpmScraper())

Step 3: Update row in scraper_registry_config (already exists from Custom HTTP):
        UPDATE scraper_registry_config
        SET strategy_class = 'NpmScraper'
        WHERE registry_key = 'npm';

Step 4: Write tests in  tests/test_npm.py

No changes to: comparison-service, recommendation-service,
               notification-service, scheduler-service, api-gateway, ui-service
```

### 18.5 Dashboard Multi-Framework View

When v2+ ecosystems are added, the Dashboard gains:

```
Filters:  Platform [All ▼]  Ecosystem [All ▼]  Language [All ▼]  Status [All ▼]

Summary:  [ 74 Android ] [ 45 iOS ] [ 120 npm ] [ 89 Python ] ...

Color-coded by update_needed regardless of ecosystem.
```

### 18.6 Notification Multi-Framework Grouping

Email and Teams notifications auto-group libraries by ecosystem:

```
📱 Mobile — Android (74 libraries)
   🔴 Mandatory: 28   🟡 Recommended: 20   ✅ OK: 26

📱 Mobile — iOS (45 libraries)
   🔴 Mandatory: 33   ✅ OK: 12

🌐 Web — npm (future)
   ...
```

---

*End of Enterprise Architecture & Development Plan v2.4*  
*Please review and confirm before development begins.*
