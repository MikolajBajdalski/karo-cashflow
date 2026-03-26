import re
from datetime import datetime


def report_text_to_html(text):
    """Convert AI report text (markdown-like) to HTML."""
    if not text:
        return ""

    lines = text.split("\n")
    html_parts = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Section header: === TITLE ===
        m = re.match(r"^===\s*(.+?)\s*===$", line)
        if m:
            html_parts.append(f'<h3 class="report-section">{m.group(1)}</h3>')
            i += 1
            continue

        # Numbered list item (1. 2. etc.)
        if re.match(r"^\d+\.\s+", line):
            html_parts.append(f"<p class=\"list-item\">{line}</p>")
            i += 1
            continue

        # Lines starting with ** (bold line)
        if line.startswith("**"):
            content = line.strip("*").strip()
            html_parts.append(f"<p><strong>{content}</strong></p>")
            i += 1
            continue

        # All-caps word followed by colon → bold
        if re.match(r"^[A-ZŁŚŻŹĆŃÓĘ]{2,}[A-ZŁŚŻŹĆŃÓĘ\s]*:", line):
            html_parts.append(f"<p><strong>{line}</strong></p>")
            i += 1
            continue

        # Blank line → paragraph break (skip)
        if line.strip() == "":
            html_parts.append("<br>")
            i += 1
            continue

        # Inline bold markers (**text**)
        line_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        html_parts.append(f"<p>{line_html}</p>")
        i += 1

    return "\n".join(html_parts)


def generate_pdf(report_text, period, entity):
    """
    Render report_text as a styled PDF.

    Args:
        report_text (str): Raw AI report text.
        period (str): Period string, e.g. "2026-03".
        entity (str): Entity name, e.g. "JDG".

    Returns:
        bytes: PDF file bytes.
    """
    from weasyprint import HTML

    body_html = report_text_to_html(report_text)
    generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    html_content = f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <title>KARO CashFlow — Raport {entity} {period}</title>
  <style>
    @page {{
      margin: 2cm;
    }}
    body {{
      font-family: Arial, sans-serif;
      font-size: 11pt;
      color: #1a1a1a;
      line-height: 1.55;
    }}
    .page-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      border-bottom: 1.5px solid #1a1a1a;
      padding-bottom: 6px;
      margin-bottom: 18px;
    }}
    .page-header .brand {{
      font-size: 14pt;
      font-weight: bold;
      letter-spacing: 0.5px;
    }}
    .page-header .meta {{
      font-size: 10pt;
      color: #444;
      text-align: right;
    }}
    h3.report-section {{
      font-size: 12pt;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-left: 3px solid #1a1a1a;
      padding-left: 8px;
      margin-top: 20px;
      margin-bottom: 8px;
    }}
    p {{
      margin: 3px 0;
    }}
    p.list-item {{
      margin-left: 14px;
    }}
    strong {{
      font-weight: bold;
    }}
    .page-footer {{
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      font-size: 8pt;
      color: #888;
      text-align: center;
      border-top: 0.5px solid #ccc;
      padding-top: 4px;
    }}
  </style>
</head>
<body>
  <div class="page-header">
    <div class="brand">KARO CashFlow</div>
    <div class="meta">{period} &nbsp;|&nbsp; {entity}</div>
  </div>

  <div class="report-body">
    {body_html}
  </div>

  <div class="page-footer">
    Wygenerowano: {generated_at}
  </div>
</body>
</html>"""

    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes
