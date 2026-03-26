from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from datetime import datetime
from app.db import get_db
from app.ai_engine import generate_report
from app.pdf_export import generate_pdf, report_text_to_html

bp = Blueprint('ai_report', __name__)

POLISH_MONTHS = {
    1: "Styczeń", 2: "Luty", 3: "Marzec", 4: "Kwiecień",
    5: "Maj", 6: "Czerwiec", 7: "Lipiec", 8: "Sierpień",
    9: "Wrzesień", 10: "Październik", 11: "Listopad", 12: "Grudzień"
}

ENTITIES = ['JDG', 'PV', 'GROUP']


def _load_report(period, entity):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, period, entity, report_text, tokens_used, created_at "
            "FROM ai_reports WHERE period = ? AND entity = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (period, entity)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _available_periods():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT period FROM ai_reports ORDER BY period DESC LIMIT 6"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _load_ceo_notes(period, entity):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT note, created_at FROM ceo_notes WHERE period = ? ORDER BY created_at DESC",
            (period,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@bp.route('/ai-report')
def index():
    now = datetime.now()
    entity = request.args.get('entity', 'JDG')
    year = int(request.args.get('year', now.year))
    month = int(request.args.get('month', now.month))
    period = f"{year:04d}-{month:02d}"

    report = _load_report(period, entity)
    available_periods = _available_periods()
    ceo_notes = _load_ceo_notes(period, entity)

    report_html = report_text_to_html(report['report_text']) if report else ''

    return render_template(
        'ai_report.html',
        report=report,
        report_html=report_html,
        entity=entity,
        year=year,
        month=month,
        period=period,
        available_periods=available_periods,
        ceo_notes=ceo_notes,
        polish_months=POLISH_MONTHS,
        entities=ENTITIES,
        now=now,
    )


@bp.route('/ai-report/generate', methods=['POST'])
def generate():
    entity = request.form.get('entity', 'JDG')
    year = int(request.form.get('year', datetime.now().year))
    month = int(request.form.get('month', datetime.now().month))

    result = generate_report(entity, year, month)

    if result.get('error'):
        flash(f"Błąd generowania raportu: {result['error']}", 'error')
    else:
        flash(
            f"Raport wygenerowany pomyślnie. Zużyto tokenów: {result['tokens_used']:,}",
            'success'
        )

    return redirect(url_for('ai_report.index', entity=entity, year=year, month=month))


@bp.route('/ai-report/note', methods=['POST'])
def save_note():
    period = request.form.get('period')
    entity = request.form.get('entity', 'JDG')
    note_text = request.form.get('note_text', '').strip()
    year = request.form.get('year', datetime.now().year)
    month = request.form.get('month', datetime.now().month)

    if note_text:
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO ceo_notes (period, note) VALUES (?, ?)",
                (period, note_text)
            )
            conn.commit()
        finally:
            conn.close()
        flash("Notatka zapisana", 'success')

    return redirect(url_for('ai_report.index', entity=entity, year=year, month=month))


@bp.route('/ai-report/pdf')
def export_pdf():
    period = request.args.get('period')
    entity = request.args.get('entity', 'JDG')

    if not period:
        flash("Brak wybranego okresu.", 'error')
        return redirect(url_for('ai_report.index'))

    report = _load_report(period, entity)
    if not report:
        flash("Brak raportu dla wybranego okresu.", 'error')
        return redirect(url_for('ai_report.index', entity=entity))

    pdf_bytes = generate_pdf(report['report_text'], period, entity)
    filename = f"KARO_CashFlow_{entity}_{period}.pdf"

    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
