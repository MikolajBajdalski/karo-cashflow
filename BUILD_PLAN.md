# KARO CashFlow — Build Plan (14 Agent Commands)

Execute commands ONE AT A TIME. Wait for agent to finish and show artifacts before sending the next command.

---

## PHASE 1: Foundation

### Command 1 — Project bootstrap
```
Create a Flask web application with the structure defined in ARCHITECTURE.md.

Create these files:
- run.py: start Flask on port 5001, debug=True, call init_db() on startup
- requirements.txt: flask, pyodbc, anthropic, weasyprint, python-dotenv
- app/__init__.py: Flask app factory
- app/db.py: init_db() function that creates all 5 SQLite tables from ARCHITECTURE.md schema, DB path: data/karo_cashflow.db (create dir if missing), include seed INSERT for category_rules
- .env.example: SQL_SERVER_USER=sa, SQL_SERVER_PASSWORD=YOUR_PASS, ANTHROPIC_API_KEY=your_key_here

Confirm with: "Done. Run: python run.py"
```

### Command 2 — SQL Server connector
```
Create app/sql_connector.py as specified in ARCHITECTURE.md.

Implement get_connection(database) and sync_subiekt(entity, date_from).

SQL Server queries to use in sync_subiekt:
- FS (sales): SELECT dok_NrPelny, dok_DataWyst, dok_PlatTermin, dok_WartBrutto, a.adrh_Nazwa, a.adrh_NIP FROM dok__Dokument d LEFT JOIN adr_Historia a ON d.dok_PlatnikAdreshId = a.adrh_Id WHERE d.dok_Typ = 2 AND d.dok_Podtyp IN (0,2,4,5) AND d.dok_DataWyst >= ?
- FZ (purchases): same join, dok_Typ=1, dok_Podtyp=0
- KP (cash in): SELECT nzf_NumerPelny, nzf_Data, nzf_Wartosc, a.adrh_Nazwa, a.adrh_NIP FROM nz__Finanse f LEFT JOIN adr_Historia a ON f.nzf_IdHistoriiAdresu = a.adrh_Id WHERE f.nzf_Typ = 17 AND f.nzf_Data >= ?
- KW (cash out): same, nzf_Typ=18
- Receivables: nzf_Typ=39, nzf_Status=1, join: nzf_IdObiektu = adrh_Id
- Payables: nzf_Typ=40, nzf_Status=1, join: nzf_IdHistoriiAdresu = adrh_Id

Apply category_rules from SQLite when inserting (match by NIP, set category + is_internal).
```

### Command 3 — CSV parsers
```
Create app/parsers/bank_csv.py and app/parsers/salary_csv.py as specified in ARCHITECTURE.md.

bank_csv.py: parse_bank_csv(filepath, account)
- Auto-detect PKO BP vs Nest Bank format by checking header row
- Parse Polish decimal format (comma as decimal separator) to float
- Insert into bank_statements table, skip duplicates (account+date+amount+description)
- Return {inserted, skipped, errors}

salary_csv.py: parse_salary_csv(filepath)
- Columns: Podmiot (JDG/PV), Miesiac (YYYY-MM), Brutto_PLN
- Insert into transactions as doc_type='SALARY', category='WYNAGRODZENIA', negative amount
- Return {inserted, skipped, errors}
```

### Command 4 — Import UI
```
Create route /import (GET) and template templates/import.html extending base.html.

Three sections:
1. SQL Server sync: buttons "Sync JDG" and "Sync PV", each POST to /import/sync/<entity> with date_from field (default: 6 months ago). Show green/red dot for connection status (check via get_connection()).
2. Bank CSV upload: file input + account dropdown (PKO_JDG, NEST_JDG, PKO_PV, NEST_PV). POST to /import/bank.
3. Salary CSV upload: file input. POST to /import/salary.

All POST routes: use flash messages for success/error, redirect back to /import.
Show last sync timestamp for each source from DB (query MAX(synced_at) from transactions by source).
```

### Command 5 — Aggregator + Costs view
```
Create app/aggregator.py with get_monthly_summary(entity, year, month) as specified in ARCHITECTURE.md.

Create route /costs and template templates/costs.html.

Show:
- Month selector dropdown + entity toggle (JDG / PV) at top
- Bar chart (Chart.js) of top 10 cost categories for selected month
- Table: category | amount PLN | % of total | delta vs prev month
- Rows where delta > 20%: amber background. Delta > 50%: red background.
- [INTERNAL] transfers shown as separate section, not in main chart.
```

---

## PHASE 2: Financial views

### Command 6 — Dashboard
```
Create route / (dashboard) and template templates/dashboard.html extending base.html.

Four KPI cards at top: Total Revenue (month), Total Costs (month), Net Cash Flow (month), Overdue Receivables total.

Line chart (Chart.js): monthly revenue vs costs for last 6 months, two series: JDG (solid) and PV (dashed).

Two tables below chart:
- Left: Top 5 overdue receivables (counterparty, amount PLN, days overdue)
- Right: Payables due in next 14 days (counterparty, amount PLN, due date)

All data from aggregator.get_monthly_summary().
```

### Command 7 — Receivables
```
Create route /receivables and template templates/receivables.html extending base.html.

Aging table with buckets: Current (not due), 1-14 days, 15-30 days, 31-60 days, 61-90 days, 90+ days.
Columns: Counterparty | Invoice number | Amount PLN | Due Date | Days Overdue
Color code: current=white, 1-14d=light yellow, 15-30d=amber, 31-60d=orange, 61+d=red.
Show bucket subtotals as summary rows.

Filters at top: entity (JDG/PV/Both), "show only overdue" checkbox.
Calculate days_overdue = today - due_date (negative = not yet due).
Data: transactions where doc_type='FS' and status='OPEN'.
```

### Command 8 — Payables
```
Create route /payables and template templates/payables.html extending base.html.

List of open payables sorted by due_date ASC.
Columns: Supplier | Invoice number | Amount PLN | Due Date | Days Until Due
Color: overdue=red background, due <=7 days=amber, due <=30 days=light yellow.

Tag rows with is_internal=1 with a gray [INTERNAL] badge.
Filter: entity (JDG/PV/Both), toggle to hide/show INTERNAL.
Data: transactions where doc_type='FZ' and status='OPEN'.
```

---

## PHASE 3: AI engine

### Command 9 — Prompt builder
```
Create app/ai_engine.py with build_prompt(entity, year, month) as specified in ARCHITECTURE.md.

Prompt structure:
1. Load ai_context/business_rules.md as system context
2. Last 3 ai_reports from DB for this entity, first 500 chars each
3. ceo_notes where period = 'YYYY-MM' or period IS NULL
4. get_monthly_summary() result formatted as clean text table (no JSON, no raw rows)
5. Fixed task: "Analyze this data. Identify: 1) anomalies vs historical average, 2) cash flow forecast next 30/60/90 days, 3) top 3 action items, 4) one-sentence executive summary."

If total exceeds 8000 tokens: truncate historical reports first, then notes.
Log estimated token count to console.
```

### Command 10 — Claude API integration
```
In app/ai_engine.py add generate_report(entity, year, month).

Call Anthropic API:
- model: 'claude-sonnet-4-5'
- max_tokens: 2000
- API key from .env: ANTHROPIC_API_KEY

On success: save to ai_reports table, return {report_text, tokens_used, period, entity}.
On error: return {error: str}. Never raise to caller.
```

### Command 11 — AI report view + PDF export
```
Create route /ai-report and template templates/ai_report.html extending base.html.

Controls: year+month dropdowns, entity toggle (JDG/PV). Button "Generate Report" POSTs to /ai-report/generate.

Display: render report_text as formatted HTML (## → h2, ** → bold). Show token count below report.

CEO notes: textarea "Add note for next report" + Save button → POST /ai-report/note → save to ceo_notes table.

History: list of last 6 reports as links (load without regenerating).

PDF export: button "Export PDF" → GET /ai-report/pdf?period=YYYY-MM&entity=X
Create app/pdf_export.py: generate_pdf(report_text, period, entity) using WeasyPrint.
Filename: KARO_CashFlow_<ENTITY>_<YYYY-MM>.pdf
```

---

## PHASE 4: Polish

### Command 12 — Navigation + base layout
```
Create templates/base.html as master layout.

Left sidebar (dark navy #1a2744, width 200px):
- App title "KARO CashFlow" at top
- Navigation links with Unicode icons:
  ▪ Dashboard (/)
  ▪ Costs (/costs)
  ▪ AI Report (/ai-report)
  ▪ Receivables (/receivables)
  ▪ Payables (/payables)
  ▪ Import Data (/import)
- Highlight active link

Top bar: current date, SQL Server status dot (green/red), last sync timestamp.
Content area: white, right of sidebar.
Sidebar collapses to icon-only at viewport width < 768px.

Update ALL existing templates to extend base.html.
```

### Command 13 — Business rules file
```
Create file ai_context/business_rules.md with this exact content:

# KARO Business Context for AI Analysis

## Entities
- KARO Roman Bajdalski (JDG): technical and medical gases, ADR transport, hydraulics, fire safety. Main revenue driver. ~700-900 sales invoices/month.
- KARO PV sp. z o.o. (PV): photovoltaics, windows installation. ~40-60 sales invoices/month.

## Internal transfers — always tag [INTERNAL], exclude from P&L totals
- NIP 8911634021 = KARO PV (largest single supplier for JDG, ~24% of JDG costs)
- NIP 8911135105 = Roman Bajdalski (owner withdrawals, salary advances)

## Known recurring items — do NOT flag as anomalies
- AEGON: insurance installments ~1092 PLN x9 per year
- Tax rolny: 3 installments (May/September/November), ~10652 PLN total annually
- FLOTEX POLSKA: fuel card, monthly ~9500 PLN (flag if >15000 PLN in a month)

## KPIs to always include in every report
- Net cash flow for period (excluding internal transfers)
- Overdue receivables: total + breakdown by aging bucket
- Top 3 cost categories by amount
- Month-over-month delta per category (flag if delta > 20%)
- Cash balance trend (if bank data available)

## Forecast guidance
- JDG: seasonal dip expected in January/February (gas consumption lower)
- PV: Q4 strongest, Q1 weakest (solar installation seasonality)
```

### Command 14 — End-to-end test
```
Run the application: python run.py

Test this complete flow and fix ALL errors encountered:
1. Open http://localhost:5001 — dashboard loads without errors
2. Go to /import — page renders with all three sections
3. Click "Sync JDG" for last 6 months — shows success flash or clear error message
4. Go to /costs — select current month, bar chart renders
5. Go to /receivables — aging table renders (may be empty if no data yet)
6. Go to /ai-report — generate report for current month JDG
7. Click "Export PDF" — file downloads

Report result as: "All 7 steps passed" or list each step that failed with the error.
```

---

## After build is complete

To start the app: `python run.py`
Open browser: `http://localhost:5001`

First use checklist:
1. Go to /import → Sync JDG (enter date from 6 months ago)
2. Go to /import → Sync PV
3. Upload bank CSVs for all 4 accounts
4. Upload salary CSV
5. Go to /ai-report → Generate first report
6. Read report → add CEO note if needed
