"""
parse_bank_csv(filepath, account) — import bank statement CSV into bank_statements.

Supported formats
-----------------
PKO BP  : headers contain 'Data operacji' and 'Kwota'
Nest Bank: headers contain 'Data' and 'Tytul'
"""

import csv
import re
from datetime import datetime
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
    # Strip currency symbols / stray characters that are not part of the number
    cleaned = re.sub(r'[^\d.\-]', '', cleaned)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_date(raw: str) -> Optional[str]:
    """
    Parse date string to ISO 'YYYY-MM-DD'.
    Accepts:
      - YYYY-MM-DD  (PKO BP)
      - DD.MM.YYYY  (Nest Bank)
    Returns None on failure.
    """
    raw = raw.strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _detect_format(fieldnames: list) -> Optional[str]:
    """Return 'PKO' or 'NEST' based on CSV header names, or None if unknown."""
    headers = [h.strip() for h in fieldnames]
    if 'Data operacji' in headers and 'Kwota' in headers:
        return 'PKO'
    if 'Data' in headers and 'Tytul' in headers:
        return 'NEST'
    return None


def _already_exists(conn, account: str, date: str, amount: float,
                    description: str) -> bool:
    row = conn.execute(
        """SELECT 1 FROM bank_statements
           WHERE account=? AND date=? AND amount=? AND description=?
           LIMIT 1""",
        (account, date, amount, description or '')
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_bank_csv(filepath: str, account: str) -> dict:
    """
    Parse a bank CSV file and insert rows into bank_statements.

    Parameters
    ----------
    filepath : path to the CSV file
    account  : one of PKO_JDG / NEST_JDG / PKO_PV / NEST_PV

    Returns
    -------
    dict  {inserted: int, skipped: int, errors: list[str]}
    """
    inserted = 0
    skipped = 0
    errors: list = []

    try:
        # Try common encodings used by Polish banks
        for encoding in ('utf-8-sig', 'cp1250', 'iso-8859-2'):
            try:
                with open(filepath, newline='', encoding=encoding) as fh:
                    sample = fh.read(2048)
                break
            except UnicodeDecodeError:
                continue
        else:
            errors.append("Cannot decode file — tried utf-8-sig, cp1250, iso-8859-2")
            return {'inserted': 0, 'skipped': 0, 'errors': errors}

        with open(filepath, newline='', encoding=encoding) as fh:
            # Some PKO exports prepend non-CSV metadata lines before the header.
            # Scan forward until we find a line that looks like a header.
            lines = fh.readlines()

        header_idx = None
        for i, line in enumerate(lines):
            stripped = line.strip().strip('"')
            if 'Data operacji' in stripped or ('Data' in stripped and 'Kwota' in stripped):
                header_idx = i
                break

        if header_idx is None:
            errors.append("Cannot locate header row in CSV file")
            return {'inserted': 0, 'skipped': 0, 'errors': errors}

        csv_block = lines[header_idx:]
        # Auto-detect delimiter: PKO BP uses ';', some exports use ','
        header_line = csv_block[0] if csv_block else ''
        delimiter = ';' if header_line.count(';') > header_line.count(',') else ','
        reader = csv.DictReader(csv_block, delimiter=delimiter)
        # Normalise fieldnames (strip whitespace / BOM / quotes)
        reader.fieldnames = [f.strip().strip('"').lstrip('\ufeff') for f in (reader.fieldnames or [])]

        fmt = _detect_format(reader.fieldnames)
        if fmt is None:
            errors.append(
                f"Unknown CSV format. Headers found: {reader.fieldnames}"
            )
            return {'inserted': 0, 'skipped': 0, 'errors': errors}

        if fmt == 'PKO':
            col_date  = 'Data operacji'
            col_amt   = 'Kwota'
            col_desc  = 'Opis operacji'
            col_bal   = 'Saldo po operacji'
        else:  # NEST
            col_date  = 'Data'
            col_amt   = 'Kwota'
            col_desc  = 'Tytul'
            col_bal   = 'Saldo'

        conn = get_db()
        try:
            for row_num, row in enumerate(reader, start=header_idx + 2):
                # Skip empty / summary rows
                raw_amount = (row.get(col_amt) or '').strip()
                if not raw_amount:
                    skipped += 1
                    continue

                amount = _to_float(raw_amount)
                if amount is None:
                    skipped += 1
                    continue

                raw_date = (row.get(col_date) or '').strip()
                date = _to_date(raw_date)
                if date is None:
                    errors.append(f"Row {row_num}: unparseable date '{raw_date}'")
                    skipped += 1
                    continue

                description = (row.get(col_desc) or '').strip()
                balance_raw = (row.get(col_bal) or '').strip()
                balance = _to_float(balance_raw)

                if _already_exists(conn, account, date, amount, description):
                    skipped += 1
                    continue

                conn.execute(
                    """INSERT INTO bank_statements
                           (account, date, amount, description, balance)
                       VALUES (?, ?, ?, ?, ?)""",
                    (account, date, amount, description, balance)
                )
                inserted += 1

            conn.commit()
        finally:
            conn.close()

    except Exception as exc:
        errors.append(f"Unexpected error: {exc}")

    print(f"[bank_csv] account={account} inserted={inserted} skipped={skipped} errors={errors}")
    return {'inserted': inserted, 'skipped': skipped, 'errors': errors}
