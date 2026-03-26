import os
from typing import Optional
import pyodbc
from app.db import get_db

_SERVER = r'192.168.6.199\INSERTGT'
_PORT = 49967
_DRIVER = 'ODBC Driver 18 for SQL Server'

# Map entity → database name on SQL Server
_DB_MAP = {
    'JDG': 'KARO_RB',
    'PV':  'KARO_PV',
}


def get_connection(database: str):
    """
    Return a pyodbc connection to the given database on the Subiekt SQL Server.
    Raises on failure — callers should catch.

    Parameters
    ----------
    database : str
        SQL Server database name (e.g. 'KARO_RB' or 'KARO_PV').
    """
    user     = os.getenv('SQL_SERVER_USER', 'sa')
    password = os.getenv('SQL_SERVER_PASSWORD', '')

    conn_str = (
        f"DRIVER={{{_DRIVER}}};"
        f"SERVER={_SERVER},{_PORT};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
        "Connection Timeout=5;"
    )
    return pyodbc.connect(conn_str, timeout=5)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_category_rules(sqlite_conn) -> list[dict]:
    """Load all category_rules rows from SQLite once per sync call."""
    cur = sqlite_conn.execute(
        "SELECT nip, name_pattern, category, is_internal FROM category_rules"
    )
    return [dict(r) for r in cur.fetchall()]


def _match_category(rules: list, nip: Optional[str], counterparty: Optional[str]):
    """
    Return (category, is_internal) for the first matching rule, or (None, 0).
    Matching priority: NIP > name_pattern.
    """
    nip = (nip or '').strip()
    counterparty = (counterparty or '').lower()

    for rule in rules:
        if rule['nip'] and nip and rule['nip'].strip() == nip:
            return rule['category'], int(rule['is_internal'])
        if rule['name_pattern'] and rule['name_pattern'].lower() in counterparty:
            return rule['category'], int(rule['is_internal'])
    return None, 0


def _already_exists(sqlite_conn, doc_number: Optional[str], entity: str) -> bool:
    """Return True if (doc_number, entity) already in transactions."""
    if not doc_number:
        return False
    row = sqlite_conn.execute(
        "SELECT 1 FROM transactions WHERE doc_number = ? AND entity = ? LIMIT 1",
        (doc_number, entity)
    ).fetchone()
    return row is not None


def _insert_row(sqlite_conn, row: dict):
    sqlite_conn.execute(
        """
        INSERT INTO transactions
            (entity, doc_type, doc_number, date, due_date,
             amount, category, counterparty, nip, status, is_internal, source, synced_at)
        VALUES
            (:entity, :doc_type, :doc_number, :date, :due_date,
             :amount, :category, :counterparty, :nip, :status, :is_internal,
             :source, CURRENT_TIMESTAMP)
        """,
        row
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync_subiekt(entity: str, date_from: str) -> dict:
    """
    Pull FS / FZ / KP / KW / Receivables / Payables from Subiekt GT (SQL Server)
    and upsert into the local SQLite transactions table.

    Parameters
    ----------
    entity    : 'JDG' or 'PV'
    date_from : ISO date string, e.g. '2024-01-01'

    Returns
    -------
    dict with keys: inserted (int), errors (list of str)
    """
    database = _DB_MAP.get(entity)
    if database is None:
        return {'inserted': 0, 'errors': [f"Unknown entity: {entity}"]}

    # --- open SQL Server connection ---
    try:
        sql_conn = get_connection(database)
    except Exception as exc:
        return {'inserted': 0, 'errors': [f"Connection failed: {exc}"]}

    sqlite_conn = get_db()
    rules = _load_category_rules(sqlite_conn)

    inserted = 0
    errors: list[str] = []

    try:
        cur = sql_conn.cursor()

        # ------------------------------------------------------------------ #
        # 1. FS — należności otwarte (nzf_Typ=39, nzf_Wartosc > 0)
        # ------------------------------------------------------------------ #
        try:
            cur.execute(
                """
                SELECT f.nzf_NumerPelny, f.nzf_Data, f.nzf_TerminPlatnosci,
                       f.nzf_WartoscPierwotna, f.nzf_Wartosc,
                       a.adrh_Nazwa, a.adrh_NIP
                FROM nz__Finanse f
                LEFT JOIN adr_Historia a ON f.nzf_IdObiektu = a.adrh_Id
                WHERE f.nzf_Typ = 39
                  AND f.nzf_Wartosc > 0
                  AND f.nzf_Data >= ?
                """,
                date_from
            )
            for r in cur.fetchall():
                doc_number, date, due_date, amount_orig, amount_remaining, counterparty, nip = r
                doc_number = str(doc_number) if doc_number else None
                if _already_exists(sqlite_conn, doc_number, entity):
                    continue
                category, is_internal = _match_category(rules, nip, counterparty)
                _insert_row(sqlite_conn, {
                    'entity': entity, 'doc_type': 'FS',
                    'doc_number': doc_number,
                    'date': str(date)[:10] if date else None,
                    'due_date': str(due_date)[:10] if due_date else None,
                    'amount': float(amount_remaining or 0),
                    'category': category, 'counterparty': counterparty,
                    'nip': nip, 'status': 'OPEN',
                    'is_internal': is_internal, 'source': 'SQL_SERVER',
                })
                inserted += 1
        except Exception as exc:
            errors.append(f"FS query error: {exc}")

        # ------------------------------------------------------------------ #
        # 2. FZ — zobowiązania otwarte (nzf_Typ=40, nzf_Wartosc > 0)
        # ------------------------------------------------------------------ #
        try:
            cur.execute(
                """
                SELECT f.nzf_NumerPelny, f.nzf_Data, f.nzf_TerminPlatnosci,
                       f.nzf_WartoscPierwotna, f.nzf_Wartosc,
                       a.adrh_Nazwa, a.adrh_NIP,
                       d.dok_NrPelny
                FROM nz__Finanse f
                LEFT JOIN adr_Historia a ON f.nzf_IdHistoriiAdresu = a.adrh_Id
                LEFT JOIN dok__Dokument d ON f.nzf_IdDokumentAuto = d.dok_Id
                WHERE f.nzf_Typ = 40
                  AND f.nzf_Wartosc > 0
                  AND f.nzf_Data >= ?
                """,
                date_from
            )
            for r in cur.fetchall():
                doc_number, date, due_date, amount_orig, amount_remaining, counterparty, nip, dok_nr = r
                doc_number = str(doc_number) if doc_number else None
                if _already_exists(sqlite_conn, doc_number, entity):
                    continue
                category, is_internal = _match_category(rules, nip, counterparty)
                _insert_row(sqlite_conn, {
                    'entity': entity, 'doc_type': 'FZ',
                    'doc_number': doc_number,
                    'date': str(date)[:10] if date else None,
                    'due_date': str(due_date)[:10] if due_date else None,
                    'amount': -abs(float(amount_remaining or 0)),
                    'category': category, 'counterparty': counterparty,
                    'nip': nip, 'status': 'OPEN',
                    'is_internal': is_internal, 'source': 'SQL_SERVER',
                })
                inserted += 1
        except Exception as exc:
            errors.append(f"FZ query error: {exc}")

        # ------------------------------------------------------------------ #
        # 3. KP — cash receipts (nzf_Typ = 17)
        # ------------------------------------------------------------------ #
        try:
            cur.execute(
                """
                SELECT f.nzf_NumerPelny, f.nzf_Data, f.nzf_Wartosc,
                       a.adrh_Nazwa, a.adrh_NIP
                FROM nz__Finanse f
                LEFT JOIN adr_Historia a ON f.nzf_IdHistoriiAdresu = a.adrh_Id
                WHERE f.nzf_Typ = 17
                  AND f.nzf_Data >= ?
                """,
                date_from
            )
            for r in cur.fetchall():
                doc_number, date, amount, counterparty, nip = r
                doc_number = str(doc_number) if doc_number else None
                if _already_exists(sqlite_conn, doc_number, entity):
                    continue
                category, is_internal = _match_category(rules, nip, counterparty)
                _insert_row(sqlite_conn, {
                    'entity': entity, 'doc_type': 'KP',
                    'doc_number': doc_number,
                    'date': str(date)[:10] if date else None,
                    'due_date': None,
                    'amount': float(amount or 0),
                    'category': category, 'counterparty': counterparty,
                    'nip': nip, 'status': 'PAID',
                    'is_internal': is_internal, 'source': 'SQL_SERVER',
                })
                inserted += 1
        except Exception as exc:
            errors.append(f"KP query error: {exc}")

        # ------------------------------------------------------------------ #
        # 4. KW — cash payments (nzf_Typ = 18)
        # ------------------------------------------------------------------ #
        try:
            cur.execute(
                """
                SELECT f.nzf_NumerPelny, f.nzf_Data, f.nzf_Wartosc,
                       a.adrh_Nazwa, a.adrh_NIP
                FROM nz__Finanse f
                LEFT JOIN adr_Historia a ON f.nzf_IdHistoriiAdresu = a.adrh_Id
                WHERE f.nzf_Typ = 18
                  AND f.nzf_Data >= ?
                """,
                date_from
            )
            for r in cur.fetchall():
                doc_number, date, amount, counterparty, nip = r
                doc_number = str(doc_number) if doc_number else None
                if _already_exists(sqlite_conn, doc_number, entity):
                    continue
                category, is_internal = _match_category(rules, nip, counterparty)
                _insert_row(sqlite_conn, {
                    'entity': entity, 'doc_type': 'KW',
                    'doc_number': doc_number,
                    'date': str(date)[:10] if date else None,
                    'due_date': None,
                    'amount': -abs(float(amount or 0)),
                    'category': category, 'counterparty': counterparty,
                    'nip': nip, 'status': 'PAID',
                    'is_internal': is_internal, 'source': 'SQL_SERVER',
                })
                inserted += 1
        except Exception as exc:
            errors.append(f"KW query error: {exc}")


        sqlite_conn.commit()

    except Exception as exc:
        errors.append(f"Unexpected error: {exc}")
        try:
            sqlite_conn.rollback()
        except Exception:
            pass
    finally:
        try:
            sql_conn.close()
        except Exception:
            pass
        try:
            sqlite_conn.close()
        except Exception:
            pass

    print(f"[sql_connector] sync_subiekt({entity}): inserted={inserted}, errors={errors}")
    return {'inserted': inserted, 'errors': errors}
