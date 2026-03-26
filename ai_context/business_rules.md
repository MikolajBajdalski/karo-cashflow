# KARO Business Context for AI Analysis

## Entities
- KARO Roman Bajdalski (JDG): technical and medical gases, ADR transport, hydraulics,
  fire safety. Main revenue driver. ~700-900 sales invoices/month.
- KARO PV sp. z o.o. (PV): photovoltaics, windows installation. ~40-60 sales invoices/month.

## Internal transfers — always tag [INTERNAL], exclude from P&L totals
- NIP 8911634021 = KARO PV (largest single supplier for JDG, ~24% of JDG costs)
- NIP 8911135105 = Roman Bajdalski (owner withdrawals, salary advances)

## Known recurring items — do NOT flag as anomalies
- AEGON: insurance installments ~1092 PLN x9 per year
- Tax rolny: 3 installments (May/September/November), ~10652 PLN total annually
- FLOTEX POLSKA: fuel card, monthly ~9500 PLN (flag ONLY if >15000 PLN in a month)

## KPIs to always include in every report
- Net cash flow for period (excluding internal transfers)
- Overdue receivables: total + breakdown by aging bucket
- Top 3 cost categories by amount
- Month-over-month delta per category (flag if delta > 20%)
- Cash balance trend (if bank data available)

## Forecast guidance
- JDG: seasonal dip expected in January/February (gas consumption lower in winter)
- PV: Q4 strongest, Q1 weakest (solar installation seasonality)
- Flag any month where costs exceed revenue as high-priority alert

## Report language
Always respond in Polish. Use direct, blunt tone — CEO wants facts and action items,
not diplomatic summaries.
