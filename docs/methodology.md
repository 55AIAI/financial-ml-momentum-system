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
calculated fields or cited quotes.

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

