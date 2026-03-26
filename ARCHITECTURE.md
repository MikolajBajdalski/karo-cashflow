# KARO CashFlow — Architecture & Database Schema

## Stack
| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + Flask (port 5001) |
| Local DB | SQLite — data/karo_cashflow.db |
| SQL Server connector | pyodbc + ODBC Driver 18 for macOS |
| Frontend | Vanilla HTML/CSS/JS + Chart.js CDN |
| AI engine | Anthropic Python SDK (claude-sonnet-4-5) |
| PDF export | WeasyPrint |
| Config | python-dotenv (.env file) |

## Project Structure
```
karo-cashflow/
├── .antigravity/rules.md
├── .env                        ← SQL_SERVER_PASSWORD, ANTHROPIC_API_KEY
├── .env.example
├── run.py                      ← python run.py to start
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── db.py                   ← init_db(), SQLite schema
│   ├── sql_connector.py        ← get_connection(), sync_subiekt()
│   ├── aggregator.py           ← get_monthly_summary()
│   ├── ai_engine.py            ← build_prompt(), generate_report()
│   ├── pdf_export.py           ← generate_pdf()
│   ├── parsers/
│   │   ├── bank_csv.py         ← parse_bank_csv()
│   │   └── salary_csv.py       ← parse_salary_csv()
│   └── routes/
│       ├── dashboard.py        ← GET /
│       ├── costs.py            ← GET /costs
│       ├── receivables.py      ← GET /receivables
│       ├── payables.py         ← GET /payables
│       ├── ai_report.py        ← GET /ai-report, POST /ai-report/generate
│       └── import_data.py      ← GET /import, POST /import/sync/<entity>
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── costs.html
│   ├── receivables.html
│   ├── payables.html
│   ├── ai_report.html
│   └── import.html
├── static/
│   ├── style.css
│   └── main.js
├── ai_context/
│   ├── business_rules.md       ← always injected into AI prompt
│   └── report_history/         ← saved reports as JSON
└── data/
    └── karo_cashflow.db        ← SQLite (auto-created)
```

## SQLite Schema (create in app/db.py)

```sql
CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity       TEXT NOT NULL,   -- 'JDG' or 'PV'
    doc_type     TEXT NOT NULL,   -- 'FS','FZ','KP','KW','BANK','SALARY'
    doc_number   TEXT,
    date         DATE NOT NULL,
    due_date     DATE,
    amount       REAL NOT NULL,   -- PLN, positive=inflow, negative=outflow
    category     TEXT,
    counterparty TEXT,
    nip          TEXT,
    status       TEXT,            -- 'OPEN', 'PAID'
    is_internal  INTEGER DEFAULT 0,
    source       TEXT,            -- 'SQL_SERVER','CSV_BANK','CSV_SALARY'
    synced_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bank_statements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account      TEXT NOT NULL,   -- 'PKO_JDG','NEST_JDG','PKO_PV','NEST_PV'
    date         DATE NOT NULL,
    amount       REAL NOT NULL,
    description  TEXT,
    balance      REAL,
    imported_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    period       TEXT NOT NULL,   -- 'YYYY-MM'
    entity       TEXT NOT NULL,   -- 'JDG','PV','GROUP'
    report_text  TEXT NOT NULL,
    tokens_used  INTEGER,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ceo_notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    period       TEXT,            -- 'YYYY-MM' or NULL (applies to all)
    note         TEXT NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS category_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nip          TEXT,
    name_pattern TEXT,
    category     TEXT NOT NULL,
    is_internal  INTEGER DEFAULT 0
);

-- Seed known rules
INSERT OR IGNORE INTO category_rules (nip, category, is_internal) VALUES
    ('8911634021', 'WEWNETRZNE', 1),
    ('8911135105', 'WYPLATY_WLASCICIEL', 0),
    ('8133605829', 'PALIWO_FLOTEX', 0);
```

## Key Functions

### sql_connector.py
- `get_connection(database)` → pyodbc connection to SQL Server
  - Server: 192.168.6.199\INSERTGT, port 1433
  - Credentials from .env: SQL_SERVER_USER, SQL_SERVER_PASSWORD
  - Timeout: 5 seconds
- `sync_subiekt(entity, date_from)` → {inserted: int, errors: list}
  - Pulls FS, FZ, KP, KW, open receivables, open payables
  - Inserts into SQLite transactions table
  - Skips duplicates by (doc_number, entity)

### aggregator.py
- `get_monthly_summary(entity, year, month)` → dict
  - Keys: revenue, costs, cash_in, cash_out, salaries, internal_transfers,
    receivables_overdue, payables_due_30d, categories {name: amount}
  - Excludes is_internal=1 from main totals (shows separately)

### ai_engine.py
- `build_prompt(entity, year, month)` → str (max 8000 tokens)
  - Part 1: content of ai_context/business_rules.md
  - Part 2: last 3 ai_reports (truncated to 500 chars each)
  - Part 3: ceo_notes for period or NULL period
  - Part 4: get_monthly_summary() as plain text table (NO raw JSON)
  - Part 5: fixed analysis task instructions
- `generate_report(entity, year, month)` → {report_text, tokens_used, period, entity}
  - Calls Claude API, saves result to ai_reports table

## CSV Formats to Support

### PKO BP bank export
Columns: 'Data operacji', 'Kwota', 'Opis operacji', 'Saldo po operacji'

### Nest Bank export
Columns: 'Data', 'Kwota', 'Tytul', 'Saldo'

Auto-detect format by checking header row. Polish decimal format (comma separator).

### Salary CSV (from Google Sheets export)
Columns: 'Podmiot' (JDG/PV), 'Miesiac' (YYYY-MM), 'Brutto_PLN'
Import as doc_type='SALARY', category='WYNAGRODZENIA', amount as negative float.

## UI Views (priority order)
1. /costs — bar chart by category, month selector, delta vs prev month
2. /ai-report — generate report, add CEO notes, export PDF, view history
3. / (dashboard) — KPI cards, 6-month trend chart, top overdue + upcoming payables
4. /receivables — aging table (buckets: current, 1-14d, 15-30d, 31-60d, 61-90d, 90d+)
5. /payables — sorted by due date, highlight overdue/upcoming, tag [INTERNAL]
6. /import — sync SQL Server, upload bank CSV, upload salary CSV

## UI Style
- Sidebar: dark navy (#1a2744), white content area, blue accents (#2E75B6)
- Sidebar icons: Unicode symbols only (no icon library)
- Top bar: current date, SQL Server connection status dot, last sync time
- Responsive: sidebar collapses to icon-only on narrow screens
- No JS modals. Flash messages only.
