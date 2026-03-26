import os
import anthropic
from app.db import get_db
from app.aggregator import get_monthly_summary

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Path to business rules context file (relative to project root)
_RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ai_context", "business_rules.md")

_TASK_INSTRUCTIONS = """\
=== Zadanie ===
Przeanalizuj powyższe dane. Twój raport musi zawierać dokładnie te sekcje:

1. PODSUMOWANIE WYKONAWCZE (1-2 zdania — najważniejsza informacja dla CEO)
2. ANOMALIE (kategorie kosztów lub przychodów odbiegające od normy historycznej;
   jeśli brak historii — porównaj do typowych proporcji dla branży)
3. PROGNOZA 30/60/90 DNI (cash flow na kolejne okresy; uwzględnij znane zobowiązania
   i sezonowość opisaną w kontekście)
4. TOP 3 DZIAŁANIA (konkretne, priorytetowe kroki dla CEO — nie ogólniki)
5. SYGNAŁY ALARMOWE (jeśli saldo gotówkowe ujemne, należności przeterminowane >X,
   lub koszt przekroczył przychód — wymień wprost)

Odpowiadaj po polsku. Bądź bezpośredni — CEO nie chce dyplomacji.
"""


def _load_business_rules():
    """Load ai_context/business_rules.md as a string."""
    try:
        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "(Plik business_rules.md nie został znaleziony.)"


def _load_historical_reports(entity, char_limit=500):
    """Return formatted string of last 3 AI reports for this entity."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT period, report_text FROM ai_reports "
            "WHERE entity = ? ORDER BY created_at DESC LIMIT 3",
            (entity,)
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    if not rows:
        return "Brak historycznych raportów."

    parts = []
    for period, text in rows:
        truncated = (text or "")[:char_limit]
        if len(text or "") > char_limit:
            truncated += "…"
        parts.append(f"=== Raport {period} ===\n{truncated}")

    return "\n\n".join(parts)


def _load_ceo_notes(entity, year, month, max_notes=None):
    """Return formatted CEO notes section, or empty string if none."""
    period = f"{year:04d}-{month:02d}"
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT note FROM ceo_notes "
            "WHERE (period = ? OR period IS NULL) "
            "ORDER BY created_at DESC",
            (period,)
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    if not rows:
        return ""

    if max_notes is not None:
        rows = rows[:max_notes]

    lines = "\n".join(f"- {row[0]}" for row in rows)
    return f"=== Notatki CEO ===\n{lines}"


def _format_financial_data(entity, year, month):
    """Return plain-text table of monthly financial summary."""
    summary = get_monthly_summary(entity, year, month)
    ym = f"{year:04d}-{month:02d}"

    revenue = summary.get("revenue", 0.0)
    costs = summary.get("costs", 0.0)
    net = revenue - costs
    cash_in = summary.get("cash_in", 0.0)
    cash_out = summary.get("cash_out", 0.0)
    salaries = summary.get("salaries", 0.0)
    internal = summary.get("internal_transfers", 0.0)
    receivables_overdue = summary.get("receivables_overdue", 0.0)
    payables_due_30d = summary.get("payables_due_30d", 0.0)
    categories = summary.get("categories", {})

    lines = [
        f"=== Dane finansowe {entity} {ym} ===",
        f"Przychody:              {revenue:>12,.2f} zł",
        f"Koszty:                 {costs:>12,.2f} zł",
        f"Cash flow netto:        {net:>12,.2f} zł",
        f"Wpływy gotówkowe (KP):  {cash_in:>12,.2f} zł",
        f"Wypłaty gotówkowe (KW): {cash_out:>12,.2f} zł",
        f"Wynagrodzenia:          {salaries:>12,.2f} zł",
        f"Przepływy wewnętrzne:   {internal:>12,.2f} zł",
        "",
        f"Należności przeterminowane: {receivables_overdue:,.2f} zł",
        f"Zobowiązania (30 dni):      {payables_due_30d:,.2f} zł",
        "",
        "Kategorie kosztów:",
    ]

    for name, amount in sorted(categories.items(), key=lambda x: -x[1]):
        lines.append(f"  {name:<30} {amount:>10,.2f} zł")

    return "\n".join(lines)


def _estimate_tokens(text):
    return len(text) / 4


def build_prompt(entity, year, month):
    """
    Build a structured AI analysis prompt for the given entity/period.

    Returns a single string ready to send to an LLM.
    """
    # --- PART 1: System context ---
    rules_text = _load_business_rules()
    part1 = (
        "Jesteś analitykiem finansowym firmy KARO. Poniżej kontekst biznesowy:\n\n"
        + rules_text
    )

    # --- PART 2: Historical reports (initial: 500 chars each) ---
    part2 = _load_historical_reports(entity, char_limit=500)

    # --- PART 3: CEO notes ---
    part3 = _load_ceo_notes(entity, year, month)

    # --- PART 4: Monthly financial summary ---
    part4 = _format_financial_data(entity, year, month)

    # --- PART 5: Task instructions (fixed) ---
    part5 = _TASK_INSTRUCTIONS

    def _assemble(p1, p2, p3, p4, p5):
        sections = [p1, p2, p4, p5]
        if p3:
            sections = [p1, p2, p3, p4, p5]
        return "\n\n".join(sections)

    full_prompt = _assemble(part1, part2, part3, part4, part5)
    estimated = _estimate_tokens(full_prompt)
    print(f"[AI] Prompt size: ~{int(estimated)} tokens")

    # --- Token budget management ---
    if estimated > 8000:
        # First: truncate historical reports to 200 chars each
        part2 = _load_historical_reports(entity, char_limit=200)
        full_prompt = _assemble(part1, part2, part3, part4, part5)
        estimated = _estimate_tokens(full_prompt)
        print(f"[AI] After truncating history to 200 chars: ~{int(estimated)} tokens")

    if estimated > 8000:
        # Remove Part 2 entirely
        part2 = ""
        full_prompt = _assemble(part1, part2, part3, part4, part5)
        estimated = _estimate_tokens(full_prompt)
        print(f"[AI] After removing history: ~{int(estimated)} tokens")

    if estimated > 8000:
        # Truncate CEO notes to 3 most recent
        part3 = _load_ceo_notes(entity, year, month, max_notes=3)
        full_prompt = _assemble(part1, part2, part3, part4, part5)
        estimated = _estimate_tokens(full_prompt)
        print(f"[AI] After truncating CEO notes: ~{int(estimated)} tokens")

    print(f"[AI] Final prompt size: ~{int(estimated)} tokens")
    return full_prompt


def generate_report(entity, year, month):
    """
    Generate an AI financial report for the given entity and period.

    Calls the Anthropic API, persists the result to ai_reports, and
    returns a result dict. Never raises — all exceptions are caught.

    Returns:
        {
            "report_text": str | None,
            "tokens_used": int,
            "period": str,
            "entity": str,
            "error": str | None
        }
    """
    period = f"{year:04d}-{month:02d}"

    try:
        # 1. Build prompt
        prompt = build_prompt(entity, year, month)

        # 2. Initialize Anthropic client
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # 3. Call API
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        # 4. Extract response
        response_text = message.content[0].text

        # 5. Extract token usage
        tokens_used = message.usage.input_tokens + message.usage.output_tokens

        # 6. Persist to ai_reports
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO ai_reports (period, entity, report_text, tokens_used) "
                "VALUES (?, ?, ?, ?)",
                (period, entity, response_text, tokens_used)
            )
            conn.commit()
        finally:
            conn.close()

        print(f"[AI] Report generated: {entity} {period}, {tokens_used} tokens")

        # 7. Return success dict
        return {
            "report_text": response_text,
            "tokens_used": tokens_used,
            "period": period,
            "entity": entity,
            "error": None
        }

    except Exception as e:
        print(f"[AI] Error generating report: {str(e)}")
        return {
            "report_text": None,
            "tokens_used": 0,
            "period": period,
            "entity": entity,
            "error": str(e)
        }
