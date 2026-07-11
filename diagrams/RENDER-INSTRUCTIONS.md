# PlantUML — How to Render (Fix for HTTP 400 Error)

## Problem

```
HTTP Status 400 – Bad Request
Request header is too large
```

This happens because the original combined file (`~23 KB`, 12 diagrams) is sent to a **Tomcat-based PlantUML HTTP server**. Tomcat's default `maxHttpHeaderSize` is **8 KB (8192 bytes)**. The encoded diagram exceeds this limit.

---

## Solution — Render Individual Diagram Files

Open **one file at a time** from `plantuml/diagrams/`:

| File | Description | Size |
|------|-------------|------|
| `01_End_to_End_Business_Workflow.puml` | **Main workflow** — all 7 steps | ~4 KB |
| `02_Business_Process_Sequence.puml` | Sequence diagram | ~2 KB |
| `03_Swimlane_Complete_Business_Workflow.puml` | Swimlane view | ~1 KB |
| `04_Business_Context_Overview.puml` | Context diagram | ~2 KB |
| `05_Current_vs_Future_Process.puml` | As-Is vs To-Be | ~1.5 KB |
| `06_Aggregation_and_Comparison_Workflow.puml` | Aggregation logic | ~2 KB |
| `07_Recommendation_Generation_Workflow.puml` | Pros/cons generation | ~2 KB |
| `08_Notification_Workflow.puml` | Email & Teams | ~1.7 KB |
| `09_Multi_Library_Processing_Loop.puml` | Multi-library loop | ~1.3 KB |
| `10_Use_Case_Diagram.puml` | Use cases | ~1.6 KB |
| `11_Business_Data_Flow.puml` | Data flow | ~1.4 KB |
| `12_Upgrade_Decision_Tree.puml` | Decision tree | ~1 KB |

### In Cursor / VS Code

1. Open `plantuml/diagrams/01_End_to_End_Business_Workflow.puml`
2. Press `Option + D` (Mac) or `Alt + D` (Windows) to preview
3. Do **not** preview the combined/index file

---

## Alternative Fixes

### Option A — Use Local PlantUML (Best)

```bash
brew install plantuml graphviz
plantuml plantuml/diagrams/*.puml
```

Output PNG/SVG files are generated locally — no HTTP server needed.

### Option B — Change VS Code / Cursor PlantUML Setting

In Settings, search for `plantuml.render` and set to:

```json
"plantuml.render": "Local"
```

Or set JAR path:

```json
"plantuml.jar": "/usr/local/bin/plantuml"
```

### Option C — Increase Tomcat Header Size (if you host PlantUML server)

In `server.xml`:

```xml
<Connector port="8080" protocol="HTTP/1.1"
           maxHttpHeaderSize="65536"
           ... />
```

Restart Tomcat after change.

---

## Recommended Starting Point

Start with:

**`plantuml/diagrams/01_End_to_End_Business_Workflow.puml`**

This contains the complete 7-step business workflow in a single renderable diagram.
