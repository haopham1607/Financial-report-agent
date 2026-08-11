"""Static configuration for the financial-report agent: language + prompts."""

# Language for all generated output (analysis, summary, highlights, risks,
# report headings, chart labels). Set to "English" to switch everything back.
REPORT_LANGUAGE = "Vietnamese"

# Search-gather prompt. A Google-Search-grounded call fills this FIXED format
# for every company — the qualitative context the numbers can't provide. The
# structure follows standard equity-research / financial-analysis reporting.
# {company} is filled in; REPORT_LANGUAGE is concatenated.
SEARCH_PROMPT = (
    '''Search the web and gather the following about the company "{company}", \
under these EXACT headings. Use actual reported information; clearly label any \
forward-looking figure as a forecast. Be concise and factual.

## Business overview
What the company does, its main business lines / divisions, and market position.

## Revenue by segment
Each business segment / division with its revenue and % share of the total — \
actual reported figures, from the most recent period a breakdown is available for. \
State CLEARLY which period the segment figures cover (e.g. full year 2025, or the \
first 6 months of 2026) — any timeframe is fine, but the period must be explicit. \
Omit only if the company has no segment breakdown at all.

## Industry & competitive position
The industry, main competitors, the company's positioning / market share, and \
relevant sector trends.

## Recent developments (last ~12 months)
Notable events: contracts, M&A, expansions, product launches, leadership \
changes, restructuring, major operational news.

## Outlook & guidance
The company's own stated targets / plans for the coming period — clearly \
labelled as forward-looking / forecast.

## Growth drivers
What is driving or dragging the company's performance — markets, products, \
macro factors.

## Risks & challenges
Key risks: competitive, regulatory, macroeconomic, and company-specific.

## Sources
A numbered list of the sources used, as markdown links.

Write everything in '''
    + REPORT_LANGUAGE
    + '''.'''
)

# Writer prompt. A plain (no-tools, schema-enforced) call fuses the ACTUAL
# numbers (source of truth, from yfinance) with the gathered context into the
# structured financial-HEALTH report. Not investment advice — no buy/sell.
# {company} and {figures} are filled in; the context is appended after.
WRITER_PROMPT = (
    '''You are a financial analyst writing a financial-HEALTH assessment of \
"{company}". This is a health assessment, NOT investment advice — do not give \
a buy/sell recommendation or a price target.

The company's ACTUAL financial figures (the SOURCE OF TRUTH for every number; \
never contradict them):
{figures}

Return a JSON object with:
1. "summary": a 3-5 sentence assessment of financial health — covering \
profitability, liquidity & solvency, and cash flow — grounded in the figures.
2. "verdict": ONE plain-language sentence on whether the company is \
financially healthy.
3. "health": one of "good", "mixed", or "weak".
4. "currency_unit": the unit of the segment figures below, e.g. "tỷ VNĐ".
5. "segments": revenue by business segment, each as \
{{"name": "...", "revenue": number}}, taken from the context. Use whatever the \
most recent available period is — any timeframe is fine (full year, half-year, \
etc.). Empty list if the context has no segment breakdown. Plain numbers only.
6. "segment_period": the period the segment figures in 5 cover, stated plainly \
(e.g. "Cả năm 2025" or "6 tháng đầu năm 2026"). This is shown on the chart so the \
breakdown is never mistaken for a full year. Empty string if "segments" is empty.
7. "highlights": short positive / neutral points (from recent developments, \
growth drivers, and strong metrics).
8. "risks": short risks or concerns (from the risks context and weak metrics).

Write "summary", "verdict", "highlights", "risks" and segment names in '''
    + REPORT_LANGUAGE
    + '''.

Gathered qualitative context to use:

'''
)
