from flask import Blueprint, render_template, request
from datetime import datetime
from app.aggregator import get_monthly_summary
from app.db import get_db

bp = Blueprint('costs', __name__)


def _available_months():
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT strftime('%Y-%m', date) AS ym FROM transactions ORDER BY ym DESC"
    ).fetchall()
    conn.close()
    return [row[0] for row in rows]


@bp.route('/costs')
def index():
    now = datetime.now()
    entity = request.args.get('entity', 'JDG')
    year = int(request.args.get('year', now.year))
    month = int(request.args.get('month', now.month))

    summary = get_monthly_summary(entity, year, month)

    # previous month for top-card deltas
    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1
    prev_summary = get_monthly_summary(entity, py, pm)

    months = _available_months()
    if not months:
        months = [now.strftime('%Y-%m')]

    return render_template(
        'costs.html',
        summary=summary,
        prev_summary=prev_summary,
        entity=entity,
        year=year,
        month=month,
        available_months=months,
        now=now,
    )
