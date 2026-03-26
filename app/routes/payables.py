from flask import Blueprint, render_template, request
from datetime import date
from app.db import get_db

bp = Blueprint('payables', __name__)


@bp.route('/payables')
def index():
    entity = request.args.get('entity', 'JDG')
    hide_internal = request.args.get('hide_internal', 'false').lower() in ('on', 'true', '1', 'yes')

    today = date.today()

    conn = get_db()

    # Build query dynamically based on filters
    params = []
    entity_clause = "AND entity = ?" if entity != 'Both' else ""
    if entity != 'Both':
        params.append(entity)

    internal_clause = "AND is_internal = 0" if hide_internal else ""

    query = f"""
        SELECT counterparty, doc_number, amount, due_date, entity, is_internal
        FROM transactions
        WHERE doc_type = 'FZ'
          AND status   = 'OPEN'
          AND due_date IS NOT NULL
          {entity_clause}
          {internal_clause}
        ORDER BY due_date ASC
    """
    rows = conn.execute(query, params).fetchall()
    conn.close()

    # Enrich rows with days_until_due
    enriched = []
    for r in rows:
        try:
            due = date.fromisoformat(r['due_date'])
        except (TypeError, ValueError):
            continue
        days_until_due = (due - today).days
        enriched.append({
            'counterparty': r['counterparty'] or '—',
            'doc_number':   r['doc_number']   or '—',
            'amount':       r['amount'],
            'due_date':     due,
            'days_until_due': days_until_due,
            'entity':       r['entity'],
            'is_internal':  bool(r['is_internal']),
        })

    # Sort: overdue first (ascending by due_date within each group),
    # then upcoming by due_date ASC
    enriched.sort(key=lambda r: r['due_date'])

    # Summary card totals
    overdue_total = sum(r['amount'] for r in enriched if r['days_until_due'] < 0)
    due_7_total   = sum(r['amount'] for r in enriched if 0 <= r['days_until_due'] <= 7)
    due_30_total  = sum(r['amount'] for r in enriched if 0 <= r['days_until_due'] <= 30)

    grand_total = sum(r['amount'] for r in enriched)

    return render_template(
        'payables.html',
        now=today,
        entity=entity,
        hide_internal=hide_internal,
        rows=enriched,
        overdue_total=overdue_total,
        due_7_total=due_7_total,
        due_30_total=due_30_total,
        grand_total=grand_total,
        grand_count=len(enriched),
    )
