from flask import Blueprint, render_template, request
from datetime import date
from app.db import get_db

bp = Blueprint('receivables', __name__)

# Bucket definitions: (key, label, min_days, max_days_inclusive)
# min_days < 0 means "future" (current), else days_overdue >= min_days
BUCKETS = [
    ('current', 'Bieżące',      None, -1),   # days_overdue < 0
    ('1_14',    '1–14 dni',     0,    14),
    ('15_30',   '15–30 dni',    15,   30),
    ('31_60',   '31–60 dni',    31,   60),
    ('61_90',   '61–90 dni',    61,   90),
    ('90plus',  'Powyżej 90',   91,   None),
]

BUCKET_COLORS = {
    'current': ('#6b7280', '#f3f4f6'),   # gray
    '1_14':    ('#854d0e', '#fefce8'),   # light yellow
    '15_30':   ('#92400e', '#fffbeb'),   # amber
    '31_60':   ('#9a3412', '#fff7ed'),   # orange
    '61_90':   ('#991b1b', '#fef2f2'),   # red
    '90plus':  ('#7f1d1d', '#fee2e2'),   # deep red
}

ROW_BG = {
    'current': '#f9fafb',
    '1_14':    '#fefce8',
    '15_30':   '#fffbeb',
    '31_60':   '#fff7ed',
    '61_90':   '#fef2f2',
    '90plus':  '#fee2e2',
}

SUBTOTAL_BG = {
    'current': '#e5e7eb',
    '1_14':    '#fef08a',
    '15_30':   '#fde68a',
    '31_60':   '#fdba74',
    '61_90':   '#fca5a5',
    '90plus':  '#f87171',
}


def _assign_bucket(days_overdue: int) -> str:
    if days_overdue < 0:
        return 'current'
    elif days_overdue <= 14:
        return '1_14'
    elif days_overdue <= 30:
        return '15_30'
    elif days_overdue <= 60:
        return '31_60'
    elif days_overdue <= 90:
        return '61_90'
    else:
        return '90plus'


@bp.route('/receivables')
def index():
    entity = request.args.get('entity', 'JDG')
    overdue_only = request.args.get('overdue_only', 'false').lower() in ('on', 'true', '1', 'yes')

    today = date.today()

    conn = get_db()
    if entity == 'Both':
        rows = conn.execute(
            """
            SELECT counterparty, doc_number, amount, due_date, entity
            FROM transactions
            WHERE doc_type = 'FS'
              AND status   = 'OPEN'
              AND due_date IS NOT NULL
            ORDER BY due_date ASC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT counterparty, doc_number, amount, due_date, entity
            FROM transactions
            WHERE doc_type = 'FS'
              AND status   = 'OPEN'
              AND due_date IS NOT NULL
              AND entity   = ?
            ORDER BY due_date ASC
            """,
            (entity,)
        ).fetchall()
    conn.close()

    # Enrich each row with days_overdue and bucket
    enriched = []
    for r in rows:
        try:
            due = date.fromisoformat(r['due_date'])
        except (TypeError, ValueError):
            continue
        days_overdue = (today - due).days
        bucket = _assign_bucket(days_overdue)
        enriched.append({
            'counterparty': r['counterparty'] or '—',
            'doc_number':   r['doc_number']   or '—',
            'amount':       r['amount'],
            'due_date':     due,
            'days_overdue': days_overdue,
            'bucket':       bucket,
            'entity':       r['entity'],
        })

    # Filter if overdue_only
    if overdue_only:
        enriched = [r for r in enriched if r['bucket'] != 'current']

    # Build bucket summary: {key: {count, total, label}}
    bucket_summary = {
        key: {'key': key, 'label': label, 'count': 0, 'total': 0.0,
              'text_color': BUCKET_COLORS[key][0], 'bg_color': BUCKET_COLORS[key][1]}
        for key, label, *_ in BUCKETS
    }
    for r in enriched:
        bs = bucket_summary[r['bucket']]
        bs['count'] += 1
        bs['total'] += r['amount']

    # Build ordered list of (bucket_key, [rows]) for the table
    bucket_order = [key for key, *_ in BUCKETS]
    grouped = {key: [] for key in bucket_order}
    for r in enriched:
        grouped[r['bucket']].append(r)

    return render_template(
        'receivables.html',
        now=today,
        entity=entity,
        overdue_only=overdue_only,
        bucket_summary=[bucket_summary[k] for k in bucket_order],
        grouped=grouped,
        bucket_order=bucket_order,
        bucket_labels={key: label for key, label, *_ in BUCKETS},
        row_bg=ROW_BG,
        subtotal_bg=SUBTOTAL_BG,
        grand_total=sum(r['amount'] for r in enriched),
        grand_count=len(enriched),
    )
