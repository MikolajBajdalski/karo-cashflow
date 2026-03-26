"""
parse_salary_csv(filepath) — import salary data into transactions.

Expected CSV columns: Podmiot, Miesiac, Brutto_PLN
"""

import csv
import re
from typing import Optional
from app.db import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(raw: str) -> Optional[float]:
    """Convert Polish decimal string (comma separator) to float, or None."""
    if not raw:
        return None
    cleaned = raw.strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
    cleaned = re.sub(r'[^\d.\-]', '', cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _doc_number(podmiot: str, miesiac: str) -> str:
    return f"SALARY-{podmiot.strip().upper()}-{miesiac.strip()}"


def _already_exists(conn, doc_number: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM transactions WHERE doc_number=? LIMIT 1",
        (doc_number,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_salary_csv(filepath: str) -> dict:
    """
    Parse a salary CSV and insert rows into transactions.

    Expected columns: Podmiot (JDG/PV), Miesiac (YYYY-MM), Brutto_PLN
    Amounts are stored as NEGATIVE floats (salary = outflow).

    Returns
    -------
    dict  {inserted: int, skipped: int, errors: list[str]}
    """
    inserted = 0
    skipped = 0
    errors: list = []

    try:
        for encoding in ('utf-8-sig', 'cp1250', 'iso-8859-2'):
            try:
                with open(filepath, newline='', encoding=encoding) as fh:
                    fh.read(512)
                break
            except UnicodeDecodeError:
                continue
        else:
            errors.append("Cannot decode file — tried utf-8-sig, cp1250, iso-8859-2")
            return {'inserted': 0, 'skipped': 0, 'errors': errors}

        with open(filepath, newline='', encoding=encoding) as fh:
            reader = csv.DictReader(fh, delimiter=',')
            # Normalise fieldnames
            reader.fieldnames = [
                f.strip().lstrip('\ufeff')
                for f in (reader.fieldnames or [])
            ]

            required = {'Podmiot', 'Miesiac', 'Brutto_PLN'}
            actual = set(reader.fieldnames or [])
            missing = required - actual
            if missing:
                errors.append(f"Missing columns: {missing}. Found: {list(actual)}")
                return {'inserted': 0, 'skipped': 0, 'errors': errors}

            conn = get_db()
            try:
                for row_num, row in enumerate(reader, start=2):
                    podmiot = (row.get('Podmiot') or '').strip().upper()
                    miesiac  = (row.get('Miesiac') or '').strip()
                    brutto   = _to_float(row.get('Brutto_PLN') or '')

                    # Basic validation
                    if podmiot not in ('JDG', 'PV'):
                        errors.append(
                            f"Row {row_num}: invalid Podmiot '{podmiot}' (expected JDG or PV)"
                        )
                        skipped += 1
                        continue

                    if not re.match(r'^\d{4}-\d{2}$', miesiac):
                        errors.append(
                            f"Row {row_num}: invalid Miesiac '{miesiac}' (expected YYYY-MM)"
                        )
                        skipped += 1
                        continue

                    if brutto is None or brutto <= 0:
                        errors.append(
                            f"Row {row_num}: invalid Brutto_PLN '{row.get('Brutto_PLN')}'"
                        )
                        skipped += 1
                        continue

                    doc_num = _doc_number(podmiot, miesiac)
                    if _already_exists(conn, doc_num):
                        skipped += 1
                        continue

                    date = f"{miesiac}-01"  # first day of the month

                    conn.execute(
                        """INSERT INTO transactions
                               (entity, doc_type, doc_number, date, due_date,
                                amount, category, counterparty, nip, status,
                                is_internal, source)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            podmiot,           # entity
                            'SALARY',          # doc_type
                            doc_num,           # doc_number
                            date,              # date
                            None,              # due_date
                            -abs(brutto),      # amount — negative (cost)
                            'WYNAGRODZENIA',   # category
                            None,              # counterparty
                            None,              # nip
                            'PAID',            # status
                            0,                 # is_internal
                            'CSV_SALARY',      # source
                        )
                    )
                    inserted += 1

                conn.commit()
            finally:
                conn.close()

    except Exception as exc:
        errors.append(f"Unexpected error: {exc}")

    print(f"[salary_csv] inserted={inserted} skipped={skipped} errors={errors}")
    return {'inserted': inserted, 'skipped': skipped, 'errors': errors}
