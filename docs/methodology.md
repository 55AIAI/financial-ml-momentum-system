# Methodology, evidence and limits

## Price calculations

The last eligible price is compared with the prices 1, 5 and 21 observations
earlier. Twenty-two observations are therefore required. The momentum score uses
unrounded returns; displayed component returns are rounded to two decimals.
Integrity checks allow a small rounding tolerance. Equal weights are allocated in
integer basis points, with the remainder assigned in deterministic score/ticker order.

Adjusted close is preferred when both close columns exist. The system does not
independently correct corporate actions or audit market-data vendors. It does not
simulate orders, slippage, transaction costs or portfolio performance.

## Historical risk and window boundaries

Let `P[0] ... P[21]` be the last 22 eligible prices, in date order.
The 21 simple returns are `r[t] = P[t] / P[t-1] - 1`. We calculate:

- Annualized volatility: `stdev(r, ddof=1) * sqrt(252) * 100`.
- Maximum drawdown: `max(1 - P[t] / max(P[0:t+1])) * 100`.

The sample standard deviation uses 20 degrees of freedom. Drawdown includes the
initial price as a possible peak and is a positive decline, from 0% to 100%.
Both are calculated before rounding to two decimals. They are price statistics,
not portfolio metrics or a forecast. A short, smooth price series can have low
volatility and a substantial drawdown; the metrics measure different properties.

The same close/adjusted-close column is used for returns and risk. Older prices
outside the last 22 observations and future prices cannot affect these risk
statistics. `risk_window_start` and `price_date` expose the exact boundaries;
`risk_max_gap_days` exposes the largest interval within them. Calculated
non-finite returns or volatility are rejected even when input prices are finite.

## Data-quality diagnostics

Price age is the number of calendar days from the latest eligible price to the
inclusive requested cutoff. The default stale threshold is 7 days; age equal
to the threshold is accepted. Set `--max-price-age-days` to a nonnegative integer.

Warnings are explicit:

- `STALE_PRICE`: age exceeds the configured threshold.
- `MIXED_PRICE_DATES`: requested tickers have different final price dates.
- `SPARSE_PRICE_WINDOW`: a risk-window gap exceeds 7 calendar days.

Warnings are retained in JSON, Markdown, terminal output and optional agent
context. They do not remove a ticker or realign its series; integrity checks can
pass with warnings. Annualization assumes consecutive session prices and 252
sessions per year. Gap warnings cannot establish completeness or identify the
correct trading calendar. A series with all gaps below 7 days may still be
incomplete. Users must verify frequency, missing observations and vendor dates.

Integrity evaluation checks finite/range/date constraints and recomputes
freshness warnings. It does not reconstruct returns or risk from a saved report:
the report does not embed every raw price. Re-run the pipeline on the input CSV
to reproduce calculations. Malformed report objects return failed checks.

## Source handling

Source metadata is explicit: ticker, filename, publication date, page and chunk
index. Future documents are excluded before reading. Resolved paths must stay
inside the report directory; reports have file/page/text limits. Text-only
extraction cannot read scanned PDFs without OCR.

Retrieval is deterministic token overlap, not semantic vector search. Irrelevant
queries return no sources; a source match alone does not establish an investment
risk level. No hardcoded Low/Medium/High macro classification remains.

## Agent validation

CrewAI is optional and imported only in explicit agent mode. The analyst and
reviewer see supplied snapshots rather than browsing or trading tools. Their
structured output passes Pydantic and deterministic checks. Exact quotes must be
present in a matching ticker source; numbers in summaries must occur among
calculated fields, that ticker's price age, the shared freshness threshold, or cited
quotes. Another ticker's age does not authorize a number in the current note.

These checks do not establish semantic entailment, completeness, forecast
quality or freedom from prompt injection. Human review is needed for model
interpretations. Supplied source dates can be incorrect, and a provider can fail.
No live API quality, financial returns, or claimed improvement from multiple
agents is asserted by offline tests.

## Reproducibility

The included 30-observation ALPHA/BETA fixture and reports are synthetic and
dated. The March report is intentionally excluded by the February demo snapshot.
JSON/CSV calculations and Markdown contents are reproducible for identical
inputs and configuration. Plot metadata and library versions can affect SVG
bytes, so byte-identical plots are not claimed.

