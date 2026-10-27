# Financial Research Assistant

A reproducible research pipeline that combines **Python-calculated momentum**
with **dated document evidence** and an optional **CrewAI analyst/reviewer chain**.
It is the consolidated workflow from the original financial and agent prototypes.

## Run the offline demo

Python 3.11–3.13 is covered by CI. No API key, model download, market connection
or database is needed for this demo.

```bash
python -m venv .venv
# Activate: .venv\Scripts\Activate.ps1, or source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py --demo
```

Open `output/report.md`. The same run creates `output/report.json`,
`output/signals.csv` and `output/momentum.svg`. The ALPHA and BETA prices,
organizations and reports are entirely synthetic.

[Read the generated sample report](docs/demo-report.md)

![Synthetic momentum chart](docs/demo-momentum.svg)

## What is checked

| Component | Behavior |
|---|---|
| Price engine | Validates positive finite prices, unique ticker/date pairs and at least 22 observations |
| Historical cutoff | Excludes prices and documents dated after the requested analysis date |
| Returns | Calculates 1-, 5- and 21-observation returns; prefers adjusted close if present |
| Historical risk | 21-return sample volatility annualized with 252 sessions; 22-price-window maximum drawdown |
| Data quality | Calendar-day price ages, configurable stale-price threshold, mixed end dates and sparse windows |
| Momentum | 0.4 × daily + 0.4 × weekly + 0.2 × monthly, before rounding |
| Example allocation | Equal weighting with integer basis points summing to 100% |
| Retrieval | Lexical matches scoped to the ticker and explicit publication date |
| Optional agents | Analyst and evidence reviewer return structured notes |
| Output checks | Validate dates, finite values, weight totals, momentum consistency and cited quotes |

This is a research workflow. It contains no trained ML model, predictive accuracy
claim or backtest. The example allocation is not an optimized portfolio.

## Analyze your own files

```bash
python main.py --csv prices.csv --symbols AAPL MSFT --as-of 2025-02-11 --reports reports --output-dir output
```

CSV columns: Symbol (or Ticker), Date in YYYY-MM-DD format, and Close
(or Adj Close). The date is inclusive. Horizons count **observations**, which
should be trading sessions in a real dataset. Sorting is automatic; duplicates
and insufficient history cause explicit errors rather than silently dropping tickers.
Duplicate header names (ignoring case and surrounding whitespace), unnamed columns
and rows with the wrong number of cells are rejected. Dates must use exactly
YYYY-MM-DD; compact and week-date forms are not accepted.

Risk fields use the same last 22 eligible observations as the monthly return.
Annualized volatility assumes consecutive trading-session prices and a 252-session
year. Drawdown is the largest historical peak-to-trough price decline in that
window, expressed as a positive percentage. Neither statistic predicts future risk.

The report and terminal warn if a ticker's latest price is more than 7 calendar
days old, if tickers end on different dates, or if any gap in a risk window
exceeds 7 calendar days. Warnings do not stop analysis or silently realign data.
The stale-price threshold is configurable:

```bash
python main.py --demo --as-of 2025-02-20 --max-price-age-days 3
```

The 7-day gap warning is a coarse diagnostic, not an exchange-calendar check.
The caller remains responsible for supplying session-frequency data. Inspect
`data_quality` in JSON and the corresponding Markdown section before comparing tickers.

A reports directory contains an index.json plus .txt, .md or text-based .pdf files:

```json
[
  {"filename": "company-report.pdf", "ticker": "AAPL", "published_at": "2025-01-15"}
]
```

Use ticker "*" only for genuinely shared macroeconomic sources. Dates are supplied
by the operator; the pipeline cannot independently prove their accuracy.
Ticker and filename values must be nonempty strings. An eligible file can appear
only once in the index, including aliases such as `report.txt` and `./report.txt`.
Use the shared ticker `*` for one document that applies to multiple companies.
Malformed or encrypted PDFs produce explicit errors; encrypted files are not decrypted.
Omit --reports to run numeric analysis without document evidence. Missing
evidence is reported explicitly and does not produce an invented risk score.

## Optional Qwen agents

```bash
python -m pip install -r requirements-agent.txt
# Configure QWEN_API_KEY in the environment or in a local .env file.
python main.py --demo --llm
```

The analyst drafts structured notes; the reviewer checks them against the same
snapshot, including data-quality diagnostics. A deterministic validator rejects unknown sources, cross-company
citations, non-verbatim quotes and unsupported numeric values. Python remains
the source of all calculated numbers.

Agent mode sends the selected calculations and excerpts to the configured Qwen
endpoint and can incur provider charges. It is explicitly opt-in.
Live provider behavior is not validated by offline tests.

## Tests and Docker

```bash
python -m unittest discover -s tests -v
docker build -t financial-research .
docker run --rm financial-research --demo
```

The 68 offline tests cover price and evidence cutoffs, known risk paths, rolling
windows, freshness thresholds, malformed files, local tool requests and CLI exports.

CI runs the offline tests, uploads the synthetic report as a workflow artifact,
and builds the Docker image and runs its offline demo in a separate job.
[Methodology and limitations](docs/methodology.md) explain exactly what the checks
establish. Docker needs a running engine; the image installs only offline
dependencies. Mount /app/output to retain container results.

## Local tool interface

The old FInal_project/main.py path delegates to the root CLI. The *_mcp.py
files expose a local newline-delimited JSON-RPC `tools/call` interface.
Each process accepts multiple requests until EOF and recovers after invalid JSON.
Requests and argument types are checked; notifications produce no reply.

Run the included synthetic requests from the repository root:

```powershell
Get-Content demo/finance-requests.jsonl | python finance_mcp.py
Get-Content demo/evidence-requests.jsonl | python pdf_mcp.py
```

On Bash, use `python finance_mcp.py < demo/finance-requests.jsonl`.
Read the [request examples and error contract](docs/local-tools.md).

These scripts are **not complete Model Context Protocol servers**: they do not
implement initialization, discovery or protocol negotiation. They are local
compatibility tools with no network listener.
