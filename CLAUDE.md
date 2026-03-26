# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
/opt/homebrew/bin/python3.11 run.py   # Starts Flask on http://0.0.0.0:5001
```

System Python (`/usr/bin/python3`) cannot load WeasyPrint due to macOS SIP blocking `DYLD_LIBRARY_PATH`. Always use Homebrew Python 3.11.

The app auto-creates the SQLite schema (`data/karo_cashflow.db`) on first run via `init_db()`. No migrations needed — schema is in `app/db.py`.

Requires a `.env` file with:
- `SQL_SERVER_USER`, `SQL_SERVER_PASSWORD` — Subiekt GT connection
- `ANTHROPIC_API_KEY` — Claude API

## Architecture

Flask app factory in `app/__init__.py` registers 6 blueprints from `app/routes/`. No ORM — raw `sqlite3` only.

**Data ingestion → SQLite → aggregation → views/AI:**
1. `sql_connector.py` — syncs invoices/payables/receivables from SQL Server (Subiekt GT) into `transactions` table
2. `parsers/bank_csv.py`, `parsers/salary_csv.py` — import CSVs into `transactions`
3. `aggregator.py` — `get_monthly_summary(entity, year, month)` is the single source of truth for financial KPIs
4. `ai_engine.py` — builds prompts from aggregated data + business context (`ai_context/business_rules.md`), calls Claude API, saves to `ai_reports` table

**Routes:**
- `/` — dashboard (KPIs, 6-month trend)
- `/costs` — cost breakdown by category
- `/receivables` — aging table
- `/payables` — open payables with due-date alerts
- `/ai-report` — generate/view/export AI reports as PDF
- `/import` — SQL Server sync + CSV uploads

**Frontend:** Vanilla HTML/CSS/JS + Chart.js CDN. Templates extend `base.html`. No JS framework.

## Key Rules

- **No ORM** — use `sqlite3` module directly
- **No frontend framework** — vanilla JS only
- **Monetary values** — stored as REAL in PLN; positive = inflow, negative = outflow
- **Internal transfers** — NIP `8911634021` (KARO PV) → `category='WEWNETRZNE'`, `is_internal=1`; always excluded from P&L totals
- **Claude API** — send aggregated monthly totals only, never raw rows; max 8000 tokens per prompt; model `claude-sonnet-4-6`
- **SQL Server unreachable** — show warning banner, do not crash, continue with SQLite data
- **AI reports** — always in Polish, direct tone; PDF filename: `KARO_CashFlow_<ENTITY>_<YYYY-MM>.pdf`

## SQL Server Schema (Subiekt GT)

Queried live via pyodbc at `192.168.6.199\INSERTGT:49967`. Databases: `KARO_RB` (entity=JDG), `KARO_PV` (entity=PV).

Key patterns:
- Sales invoices (FS): `dok_Typ=2`; JDG: `dok_Podtyp IN (0,2,4,5)`; PV: `dok_Podtyp IN (0,1,4,5)` (podtyp 1 = serwis)
- Purchase invoices (FZ): `dok_Typ=1`, `dok_Podtyp=0`
- Open receivables: `nzf_Typ=39`, `nzf_Status=1`; join `nzf_IdObiektu = adrh_Id`
- Open payables: `nzf_Typ=40`, `nzf_Status=1`; join `nzf_IdHistoriiAdresu = adrh_Id`
- Cash in/out (KP/KW): `nzf_Typ=17/18`; amount in `nzf_Wartosc`
- Counterparty: `adrh_Nazwa`, NIP: `adrh_NIP` in table `adr_Historia`

## Entities

- **JDG** — sole proprietorship (gases, ADR transport)
- **PV** — stolarka otworowa (windows and doors); main suppliers: DRUTEX, BRK WINDOWS
- Reports can also cover **GROUP** (combined view)
