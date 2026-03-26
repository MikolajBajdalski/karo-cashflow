from flask import Blueprint, render_template
from datetime import datetime
from app.aggregator import get_monthly_summary
from app.db import get_db

bp = Blueprint('dashboard', __name__)

# Polish month abbreviations
_PL_MONTHS = [
    'Sty', 'Lut', 'Mar', 'Kwi', 'Maj', 'Cze',
    'Lip', 'Sie', 'Wrz', 'Paź', 'Lis', 'Gru'
]


def _month_label(year, month):
    return f"{_PL_MONTHS[month - 1]} {year}"


def _prev_month(year, month, steps=1):
    """Return (year, month) going `steps` months back."""
    total = (year * 12 + month - 1) - steps
    return total // 12, total % 12 + 1


def _overdue_receivables(conn):
    """Top-5 overdue FS (not internal), by days overdue desc."""
    sql = """
        SELECT
            counterparty,
            SUM(amount)                                            AS total,
            CAST(julianday('now') - julianday(MIN(due_date)) AS INTEGER) AS days_overdue
        FROM transactions
        WHERE doc_type = 'FS'
          AND status   = 'OPEN'
          AND due_date IS NOT NULL
          AND due_date < date('now')
          AND is_internal = 0
        GROUP BY counterparty
        ORDER BY days_overdue DESC
        LIMIT 5
    """
    return conn.execute(sql).fetchall()


def _upcoming_payables(conn):
    """FZ due within next 14 days (open), sorted by due_date asc."""
    sql = """
        SELECT
            counterparty,
            ABS(amount)  AS total,
            due_date,
            is_internal
        FROM transactions
        WHERE doc_type = 'FZ'
          AND status   = 'OPEN'
          AND due_date BETWEEN date('now') AND date('now', '+14 days')
        ORDER BY due_date ASC
    """
    return conn.execute(sql).fetchall()


@bp.route('/')
def index():
    now = datetime.now()
    year, month = now.year, now.month

    # ── Current-month summaries ──────────────────────────────────────────────
    jdg = get_monthly_summary('JDG', year, month)
    pv  = get_monthly_summary('PV',  year, month)

    revenue = jdg['revenue'] + pv['revenue']
    costs   = jdg['costs']   + pv['costs']
    cf_net  = revenue - costs
    overdue = jdg['receivables_overdue'] + pv['receivables_overdue']

    # ── Last 6 months for chart ──────────────────────────────────────────────
    chart_labels   = []
    chart_jdg_rev  = []
    chart_pv_rev   = []

    for i in range(5, -1, -1):          # 5 months ago → current
        y, m = _prev_month(year, month, i)
        chart_labels.append(_month_label(y, m))
        s_jdg = get_monthly_summary('JDG', y, m)
        s_pv  = get_monthly_summary('PV',  y, m)
        chart_jdg_rev.append(round(s_jdg['revenue'], 2))
        chart_pv_rev.append(round(s_pv['revenue'],  2))

    # ── Tables ───────────────────────────────────────────────────────────────
    conn = get_db()
    overdue_rows   = _overdue_receivables(conn)
    payable_rows   = _upcoming_payables(conn)
    conn.close()

    return render_template(
        'dashboard.html',
        now=now,
        revenue=revenue,
        costs=costs,
        cf_net=cf_net,
        overdue=overdue,
        chart_labels=chart_labels,
        chart_jdg_rev=chart_jdg_rev,
        chart_pv_rev=chart_pv_rev,
        overdue_rows=overdue_rows,
        payable_rows=payable_rows,
    )
