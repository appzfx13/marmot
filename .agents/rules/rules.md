---
trigger: always_on
---

# Marmot AI Development & Automation Rules

All automated AI agents, subagents, and developers working on the Marmot codebase MUST strictly adhere to the following rules without exception.

---

## 1. Scope & Minimality (Required Changes Only)
- Make **only strictly required changes** to fulfill the specific prompt or task.
- Never perform unsolicited refactoring, code reorganization, or stylistic rewrites on untouched files or methods.
- Preserve all existing comments, type annotations, and logic in unrelated code sections.

---

## 2. Docstring & Documentation Limits
- **Maximum 1 to 2 lines per docstring** across all functions, methods, classes, and modules.
- Keep comments concise, high-signal, and factual. Avoid verbose explanations or boilerplate commentary.

---

## 3. Formatting & Space Accountability
- **Every whitespace change is accountable.**
- Never introduce trailing whitespace, unnecessary blank lines, or arbitrary indentation shifts.
- Maintain standard PEP 8 formatting for Python (`apps/`, `marmot/`) and `gofmt` conventions for Go (`go-app/`).

---

## 4. Import Hygiene
- Keep import sections clean and minimal.
- Remove all unused imports immediately.
- Group imports logically:
  1. Standard library imports
  2. Third-party packages (Django, Go modules)
  3. Local application imports

---

## 5. UI Layout & Profile Security Policy
- **Page Container Uniformity:** Maintain strict full-width container layout (`col-12`) across all pages, including Profile Settings and Admin Dashboards.
- **User Profile Field Security:**
  - `username`: Always read-only.
  - `phone_number`: Read-only for standard users.
  - `Verification Badges`: Read-only status badges for standard users.
  - `Broker Credentials`: Cannot be modified by regular users once created (Admin/Developer role required).
  - `Trade Control & Freeze Flags` (`trade_eligibility`, `is_blocked`, `primary_freeze`, `final_freeze`): Always read-only for standard users.
- **Navigation Structure:** The Profile settings link belongs exclusively in the top-right profile dropdown menu.

---

## 6. Architecture & Dual-Engine Integration Rules
- **Django Responsibility:** Manages relational entities, authentication, HTMX views, REST APIs, and dispatches background tasks via Redis Pub/Sub (`marmot:tasks:control`).
- **Go Responsibility:** Handles high-throughput streaming, WebSockets (`ws/hub.go`), Parquet reading/writing, and compute-intensive backtesting worker pools (`workers/`).
- **Data Parquet Storage:** Historical option datasets must always adhere to the date-partitioned structure under `/app/backup/{user_id}/{task_id}/`.
- **Database Safety:** Always create and verify Django migrations for schema changes (`python manage.py makemigrations`) without breaking existing relational foreign keys.
