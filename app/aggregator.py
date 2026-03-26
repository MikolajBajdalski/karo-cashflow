import sqlite3
from app.db import get_db


def _q(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return 0.0
    return row[0] or 0.0


def _period(year, month):
    return f"{year:04d}-{month:02d}"


def _entity_clause(entity):
    """Return (WHERE fragment, params list) for entity filter."""
    if entity == 'GROUP':
        return "entity IN ('JDG','PV')", []
    return "entity = ?", [entity]


def get_monthly_summary(entity, year, month):
    conn = get_db()
    ym = _period(year, month)

    # previous month
    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1
    prev_ym = _period(py, pm)

    ent_clause, ent_params = _entity_clause(entity)
    internal_exclude = "AND is_internal = 0" if entity == 'GROUP' else ""

    def month_sum(doc_type, use_abs=False, extra=""):
        amount_expr = "SUM(ABS(amount))" if use_abs else "SUM(amount)"
        sql = f"""
            SELECT {amount_expr} FROM transactions
            WHERE {ent_clause}
              AND doc_type = ?
              AND strftime('%Y-%m', date) = ?
              {internal_exclude}
              {extra}
        """
        return _q(conn, sql, ent_params + [doc_type, ym])

    revenue = month_sum('FS')
    costs = month_sum('FZ', use_abs=True)
    cash_in = month_sum('KP')
    cash_out = month_sum('KW', use_abs=True)
    salaries = month_sum('SALARY', use_abs=True)

    # internal transfers
    if entity == 'GROUP':
        internal_transfers = 0.0
    else:
        it_sql = f"""
            SELECT SUM(ABS(amount)) FROM transactions
            WHERE {ent_clause} AND is_internal = 1
              AND strftime('%Y-%m', date) = ?
        """
        internal_transfers = _q(conn, it_sql, ent_params + [ym])

    # overdue receivables
    recv_sql = f"""
        SELECT SUM(amount) FROM transactions
        WHERE {ent_clause}
          AND doc_type = 'FS' AND status = 'OPEN'
          AND due_date IS NOT NULL
          AND due_date < date('now')
          {internal_exclude}
    """
    receivables_overdue = _q(conn, recv_sql, ent_params)

    # payables due in next 30 days
    pay_sql = f"""
        SELECT SUM(ABS(amount)) FROM transactions
        WHERE {ent_clause}
          AND doc_type = 'FZ' AND status = 'OPEN'
          AND due_date BETWEEN date('now') AND date('now', '+30 days')
          {internal_exclude}
    """
    payables_due_30d = _q(conn, pay_sql, ent_params)

    # cost categories (negative amounts, current month)
    cat_sql = f"""
        SELECT category, SUM(ABS(amount)) FROM transactions
        WHERE {ent_clause}
          AND strftime('%Y-%m', date) = ?
          AND is_internal = 0
          AND category IS NOT NULL
          AND amount < 0
        GROUP BY category
    """
    categories = {
        row[0]: row[1] or 0.0
        for row in conn.execute(cat_sql, ent_params + [ym]).fetchall()
    }

    # same for previous month
    prev_cat_sql = f"""
        SELECT category, SUM(ABS(amount)) FROM transactions
        WHERE {ent_clause}
          AND strftime('%Y-%m', date) = ?
          AND is_internal = 0
          AND category IS NOT NULL
          AND amount < 0
        GROUP BY category
    """
    prev_month_categories = {
        row[0]: row[1] or 0.0
        for row in conn.execute(prev_cat_sql, ent_params + [prev_ym]).fetchall()
    }

    conn.close()

    return {
        'revenue': revenue,
        'costs': costs,
        'cash_in': cash_in,
        'cash_out': cash_out,
        'salaries': salaries,
        'internal_transfers': internal_transfers,
        'receivables_overdue': receivables_overdue,
        'payables_due_30d': payables_due_30d,
        'categories': categories,
        'prev_month_categories': prev_month_categories,
    }
