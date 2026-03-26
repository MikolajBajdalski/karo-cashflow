"""
/import routes — SQL Server sync, bank CSV upload, salary CSV upload.
"""

import os
import tempfile
from datetime import date, timedelta

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash,
)

from app.db import get_db
from app.sql_connector import get_connection, sync_subiekt
from app.parsers.bank_csv import parse_bank_csv
from app.parsers.salary_csv import parse_salary_csv

bp = Blueprint('import_data', __name__)

_ACCOUNTS = ('PKO_JDG', 'NEST_JDG', 'PKO_PV', 'NEST_PV')
_DEFAULT_MONTHS_BACK = 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sql_status():
    """Return (ok: bool, message: str) for SQL Server connectivity."""
    try:
        conn = get_connection('KARO_RB')
        conn.close()
        return True, 'Połączono z SQL Server'
    except Exception as exc:
        short = str(exc).split('\n')[0][:120]
        return False, f'Brak połączenia: {short}'


def _last_sql_sync(entity: str):
    conn = get_db()
    row = conn.execute(
        "SELECT MAX(synced_at) FROM transactions WHERE source='SQL_SERVER' AND entity=?",
        (entity,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _last_bank_import(account: str):
    conn = get_db()
    row = conn.execute(
        "SELECT MAX(imported_at) FROM bank_statements WHERE account=?",
        (account,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _last_salary_import():
    conn = get_db()
    row = conn.execute(
        "SELECT MAX(synced_at) FROM transactions WHERE source='CSV_SALARY'"
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _default_date_from() -> str:
    """ISO date string 6 months ago."""
    d = date.today() - timedelta(days=30 * _DEFAULT_MONTHS_BACK)
    return d.strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# GET /import
# ---------------------------------------------------------------------------

@bp.route('/import')
def import_page():
    sql_ok, sql_msg = _sql_status()

    last_sync = {
        'JDG': _last_sql_sync('JDG'),
        'PV':  _last_sql_sync('PV'),
    }

    last_bank = {acc: _last_bank_import(acc) for acc in _ACCOUNTS}
    last_salary = _last_salary_import()
    default_from = _default_date_from()

    return render_template(
        'import.html',
        sql_ok=sql_ok,
        sql_msg=sql_msg,
        last_sync=last_sync,
        last_bank=last_bank,
        last_salary=last_salary,
        accounts=_ACCOUNTS,
        default_from=default_from,
    )


# ---------------------------------------------------------------------------
# POST /import/sync/<entity>
# ---------------------------------------------------------------------------

@bp.route('/import/sync/<entity>', methods=['POST'])
def sync_entity(entity):
    if entity not in ('JDG', 'PV'):
        flash(f'Nieznana encja: {entity}', 'danger')
        return redirect(url_for('import_data.import_page'))

    date_from = request.form.get('date_from', _default_date_from()).strip()

    result = sync_subiekt(entity, date_from)

    if result['errors'] and result['inserted'] == 0:
        flash(f'{entity} – błąd synchronizacji: {result["errors"][0]}', 'danger')
    else:
        msg = f'{entity} – zsynchronizowano {result["inserted"]} rekordów'
        if result['errors']:
            msg += f' (ostrzeżenia: {len(result["errors"])})'
        flash(msg, 'success')

    return redirect(url_for('import_data.import_page'))


# ---------------------------------------------------------------------------
# POST /import/bank
# ---------------------------------------------------------------------------

@bp.route('/import/bank', methods=['POST'])
def import_bank():
    f = request.files.get('file')
    account = request.form.get('account', '').strip()

    if not f or not f.filename:
        flash('Nie wybrano pliku CSV.', 'danger')
        return redirect(url_for('import_data.import_page'))

    if account not in _ACCOUNTS:
        flash(f'Nieznane konto: {account}', 'danger')
        return redirect(url_for('import_data.import_page'))

    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
        tmp_path = tmp.name
        f.save(tmp_path)

    try:
        result = parse_bank_csv(tmp_path, account)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if result['errors'] and result['inserted'] == 0:
        flash(f'Bank CSV – błąd: {result["errors"][0]}', 'danger')
    else:
        msg = (f'{account} – zaimportowano {result["inserted"]} wierszy'
               f' (pominięto: {result["skipped"]})')
        if result['errors']:
            msg += f' | ostrzeżenia: {len(result["errors"])}'
        flash(msg, 'success')

    return redirect(url_for('import_data.import_page'))


# ---------------------------------------------------------------------------
# POST /import/salary
# ---------------------------------------------------------------------------

@bp.route('/import/salary', methods=['POST'])
def import_salary():
    f = request.files.get('file')

    if not f or not f.filename:
        flash('Nie wybrano pliku CSV.', 'danger')
        return redirect(url_for('import_data.import_page'))

    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
        tmp_path = tmp.name
        f.save(tmp_path)

    try:
        result = parse_salary_csv(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if result['errors'] and result['inserted'] == 0:
        flash(f'Salary CSV – błąd: {result["errors"][0]}', 'danger')
    else:
        msg = (f'Wynagrodzenia – zaimportowano {result["inserted"]} wierszy'
               f' (pominięto: {result["skipped"]})')
        if result['errors']:
            msg += f' | ostrzeżenia: {len(result["errors"])}'
        flash(msg, 'success')

    return redirect(url_for('import_data.import_page'))
