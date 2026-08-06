"""Static configuration for the financial-report research agent."""

# Language for all generated output (research, summary, highlights, risks,
# report headings, chart labels). Set to "English" to switch everything back.
REPORT_LANGUAGE = "Vietnamese"

RESEARCH_PROMPT = (
    '''Research the financial performance and health of the company \
"{company}", drawing on its most recent audited / consolidated financial \
statements and reputable financial sources.

Your report has TWO parts. Part 1 (the DATA section) is the most important \
and comes FIRST; Part 2 is the narrative analysis.

=== PART 1: DATA (required — state every figure below) ===
Report each figure explicitly and clearly labelled, as an ACTUAL REPORTED \
number (never a forecast, never a growth rate in place of the value). Use ONE \
consistent currency unit for all monetary values and state that unit. You may \
present this as markdown tables or as clearly-labelled lines — either is \
fine — but every figure that exists MUST be present and findable. \
Completeness matters far more than formatting.

For each of the last 4 COMPLETED fiscal years (oldest to newest) — use only \
years with actual reported results, NOT plan/forecast/target years such as \
"Kế hoạch" or "Dự báo" (put any forward guidance in Part 2) — state:
- TOTAL CONSOLIDATED REVENUE for the year — the single most important figure; \
never omit it, state it for every year
- Net income (profit after tax)
- Gross margin (%), Operating margin (%), Net margin (%)

For the most recent fiscal year, also state:
- Cash + short-term investments
- Total interest-bearing debt (loans & bonds only, NOT total liabilities)
- Total equity
- Debt-to-equity ratio (%)
- Current ratio (x)
- Operating cash flow
- Free cash flow
- Revenue by business segment / division (each segment's revenue). Omit only \
if the company genuinely has no segment breakdown.

=== PART 2: NARRATIVE ANALYSIS ===
After the DATA section, write analysis covering:
1. Performance and growth trajectory over the years shown.
2. Profitability and margin analysis.
3. Balance-sheet strength — leverage, liquidity, cash vs debt position.
4. Cash-flow quality — operating cash flow vs reported profit, free cash \
flow, capital expenditure.
5. Recent financial developments and management guidance (clearly LABEL any \
forward-looking / forecast number as a forecast).
6. Key financial risks.
7. A short overall assessment of the company's financial health.

Sources — this matters as much as the figures:
- For every DATA figure, prefer PRIMARY and authoritative sources: the \
company's audited / consolidated financial statements and annual reports, its \
investor-relations disclosures, and official stock-exchange or regulatory \
filings (e.g. SEC EDGAR 10-K / 20-F for US-listed firms; the relevant \
national exchange's disclosures elsewhere). Reputable financial-data \
providers that tabulate ACTUAL historical results are also good — for \
Vietnamese companies e.g. cafef.vn or vietstock.vn; for other markets, \
comparable established databases.
- Do NOT take a reported figure from brokerage / securities-firm research \
notes or price-target reports — those are forward-looking (forecasts, \
targets) and cause plan figures to be mistaken for actuals. Cite them only \
for narrative context in Part 2, clearly labelled as forecasts.
- Do NOT rely on user-uploaded document sites (e.g. studocu, scribd) or \
crowd-edited pages for any figure.

Rules:
- Every figure in the DATA section must be an ACTUAL reported figure. \
Forecasts and projections belong only in the narrative and must be labelled \
as such.
- Use one consistent currency unit throughout and state it.
- Attribute figures to their sources.
- Write the entire report in '''
    + REPORT_LANGUAGE
    + '''. Keep the numbered source list at the end exactly as markdown \
links, regardless of language.'''
)

# Targeted second-pass prompt: recover total revenue per year when the main
# extraction misses it (usually because the agent stated it only in prose).
# {years_line} anchors the model to the years the main pass already found, so
# it can't shift a figure to the wrong year or invent phantom years.
REVENUE_PROMPT = (
    '''From the financial research text below, extract TOTAL CONSOLIDATED \
REVENUE (in Vietnamese "doanh thu hợp nhất", i.e. total net revenue) for \
{years_line}

Read it from a table if present, otherwise from the narrative prose — it is \
usually stated plainly (e.g. "doanh thu hợp nhất đạt 58.580 tỷ VNĐ"). Use \
only ACTUAL reported figures, never forecast/plan/target years (Kế hoạch, Dự \
báo). Attach each figure to the fiscal year it ACTUALLY refers to; never \
shift a figure to a different year, and never invent years the text does not \
support. Use null for any year whose total revenue is not stated.

Numbers — output a plain number whose only punctuation is a "." decimal \
point. Vietnamese sources use "." as the thousands separator, so "58.580 tỷ" \
means 58580 (in billions); keep every year on the same scale.

The research text:

'''
)

NARRATIVE_PROMPT = (
    """Below is a financial research report about a company. Extract the \
QUALITATIVE assessment from it. The numeric financials (revenue, margins, \
balance sheet, cash flow) are sourced separately, so do NOT return those.

Return a JSON object with:
1. "summary": a 3-5 sentence overall assessment of the company's financial \
health, in plain text.
2. "verdict": ONE short plain-language sentence a non-expert could understand, \
on whether the company is financially healthy.
3. "health": one of "good", "mixed", or "weak".
4. "currency_unit": the unit the report's monetary values use, e.g. "tỷ VNĐ" \
or "USD billion" (used only for the segment figures below).
5. "segments": revenue by business segment / division for the most recent \
year, each as {"name": "...", "revenue": number in currency_unit}. Empty list \
if the report has no segment breakdown. Output segment revenue as a plain \
number (no thousands separators; "." is the decimal point).
6. "highlights": a list of short positive or neutral financial highlights.
7. "risks": a list of short financial risks or concerns.

Write "summary", "verdict", "highlights", "risks", and segment names in """
    + REPORT_LANGUAGE
    + """.

The report:

"""
)

EXTRACT_PROMPT = (
    """Below is a financial research report about a company. Extract \
structured data from it.

The report SHOULD contain three data tables (Table 1/2/3), but sometimes it \
is written as narrative prose with the figures inline and NO tables at all. \
Handle both: when a table is present, read from it; when the tables are \
absent, extract the SAME fields from the prose — scan the entire text for \
every year-tagged revenue and profit figure, the margins, the balance-sheet \
and cash-flow numbers, and the segment revenues. A missing table is NOT a \
reason to return nulls; only return null when a figure is genuinely absent \
from the whole report.

Return a JSON object with these fields:
1. "summary": a 3-5 sentence overall assessment of the company's financial \
health, in plain text.
1b. "verdict": ONE short plain-language sentence a non-expert could \
understand, summarizing whether the company is financially healthy.
1c. "health": one of "good", "mixed", or "weak" — an overall rating of the \
company's financial health.
2. "currency_unit": the single unit that the revenue and net_income numbers \
below are expressed in, e.g. "USD billions" or "VND billions". Normalize \
every revenue and net_income figure to this ONE unit.
3. "financials": read the year-by-year figures from the DATA section if \
present, otherwise from the figures stated in the prose. One object per \
fiscal year (oldest first). Include ONLY actual reported / completed fiscal \
years — do NOT include forecast, plan, target or projected years (e.g. "2026 \
(Kế hoạch)", "Dự báo", "Dự kiến", "2026F", "2026E"); those belong in the \
narrative fields, never here. Each object has:
   - "year": e.g. "2024"
   - "revenue": TOTAL CONSOLIDATED REVENUE ("doanh thu hợp nhất") for that \
year, as a number in currency_unit. This is the most important figure — if \
it is not in a table, find it in the prose (e.g. "doanh thu hợp nhất đạt \
58.580 tỷ"). Use null only if it is genuinely absent for that year.
   - "net_income": the net income (profit after tax) as a number in \
currency_unit, or null
4. "margins": from the most recent year's row in Table 1 — {"gross": Gross \
Margin %, "operating": Operating Margin %, "net": Net Margin %} as numbers \
(e.g. 18.5 for 18.5%), or null for any not given.
4b. "segments": read from "Table 3 — Revenue by Business Segment". List each \
row as {"name": "...", "revenue": the Revenue cell as a number in \
currency_unit}. Empty list if there is no segment table.
4c. "balance_sheet": read from "Table 2 — Balance Sheet & Cash Flow". \
{"cash": the "Cash + short-term investments" value, "debt": the "Total \
interest-bearing debt" value, "debt_to_equity": the "Debt-to-equity ratio \
(%)" value as a number e.g. 40, "current_ratio": the "Current ratio (x)" \
value as a number e.g. 1.4}. All monetary values in currency_unit. Use null \
for any row not present.
4d. "cash_flow": read from "Table 2" — {"operating": the "Operating cash \
flow" value, "free": the "Free cash flow" value}, in currency_unit. Use \
null if not present.
5. "highlights": a list of short positive or neutral financial highlights.
6. "risks": a list of short financial risks or concerns.

IMPORTANT — number formats differ by country; figure out which convention \
each number uses from context, then output a plain number whose ONLY \
punctuation is a "." decimal point (no thousands separators):
- US / UK / most English sources: "," is the thousands separator and "." is \
the decimal point. So "391,035.5" means 391035.5 and "1,234" means 1234.
- Vietnamese / most European sources: "." is the thousands separator and \
"," is the decimal point. So "40.636" means 40636 and "23,2%" means 23.2.
- Decide per number: a group of exactly 3 digits after the separator (e.g. \
"40.636", "391,035") is a THOUSANDS group; 1-2 digits after it (e.g. \
"23,2", "18.5") is a DECIMAL. When a number has both separators, the \
LAST one is the decimal point ("1,234.56" -> 1234.56; "1.234,56" -> \
1234.56).
- Watch scale words: "tỷ"/"billion", "triệu"/"million", "nghìn"/"thousand" \
— keep every figure in the ONE currency_unit you chose, converting scales \
as needed.
- Actively pull every year-tagged figure. Only use null when the figure is \
genuinely absent — do not default to null just because it is in prose.
- Prefer figures labelled as actual/reported over forecast/projected ones.
- CONSISTENCY CHECK — revenue, net income, cash, debt and the cash-flow \
figures are ALL in the one currency_unit, so they must share the same scale. \
Net income is normally 5-25% of revenue, and cash and debt are usually the \
same order of magnitude as revenue. If any of these comes out roughly 1000x \
smaller or larger than the others (e.g. revenue 70000 but net income 11.2), \
you mis-read a thousands separator — re-read it so every monetary figure is \
on the same scale.

Write "summary", "verdict", "highlights", "risks", and segment names in """
    + REPORT_LANGUAGE
    + """. Keep all numbers as plain numbers (no units, no thousands \
separators, use "." as the decimal point).

The report:

"""
)
