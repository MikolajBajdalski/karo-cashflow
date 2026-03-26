import time
from datetime import datetime
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

# Simple in-memory cache for SQL Server status (avoid hitting network every request)
_sql_cache = {'ok': None, 'msg': '', 'ts': 0}
_SQL_CACHE_TTL = 60  # seconds


def _get_sql_status():
    now = time.time()
    if now - _sql_cache['ts'] < _SQL_CACHE_TTL and _sql_cache['ok'] is not None:
        return _sql_cache['ok'], _sql_cache['msg']
    try:
        from app.sql_connector import get_connection
        conn = get_connection('KARO_RB')
        conn.close()
        _sql_cache.update(ok=True, msg='Połączono', ts=now)
    except Exception as e:
        _sql_cache.update(ok=False, msg=str(e).split('\n')[0][:80], ts=now)
    return _sql_cache['ok'], _sql_cache['msg']


def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.secret_key = 'karo-cashflow-secret-key-change-in-prod'

    # ── Dashboard (main, route '/') ──────────────────────────────────────────
    from app.routes.dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)

    # ── Import data ──────────────────────────────────────────────────────────
    from app.routes.import_data import bp as import_data_bp
    app.register_blueprint(import_data_bp)

    # ── Costs ─────────────────────────────────────────────────────────────────
    from app.routes.costs import bp as costs_bp
    app.register_blueprint(costs_bp)

    # ── Receivables ───────────────────────────────────────────────────────────
    from app.routes.receivables import bp as receivables_bp
    app.register_blueprint(receivables_bp)

    # ── Payables ──────────────────────────────────────────────────────────────
    from app.routes.payables import bp as payables_bp
    app.register_blueprint(payables_bp)

    # ── AI Report ─────────────────────────────────────────────────────────────
    from app.routes.ai_report import bp as ai_report_bp
    app.register_blueprint(ai_report_bp)

    # ── Global template context ───────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        from app.db import get_db
        sql_ok, sql_msg = _get_sql_status()
        try:
            db = get_db()
            row = db.execute(
                "SELECT MAX(synced_at) FROM transactions WHERE source='SQL_SERVER'"
            ).fetchone()
            db.close()
            last_sync_time = row[0] if row and row[0] else None
        except Exception:
            last_sync_time = None
        return dict(
            now=datetime.now(),
            sql_ok=sql_ok,
            sql_msg=sql_msg,
            last_sync_time=last_sync_time,
        )

    return app
