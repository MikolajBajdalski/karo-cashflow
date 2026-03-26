from flask import Flask
from dotenv import load_dotenv

load_dotenv()


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

    return app
