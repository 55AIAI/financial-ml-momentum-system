"""Reproducible financial research from a dated price CSV and document index."""
import argparse
import csv
import json
import math
from pathlib import Path

from evidence import load_evidence, retrieve
from finance_mcp import compute_short_term_signals

BASE = Path(__file__).resolve().parent


def build_report(csv_path, symbols, as_of, reports_dir=None, use_llm=False):
    signals = compute_short_term_signals(symbols, csv_path, as_of)
    records = load_evidence(reports_dir, as_of) if reports_dir else []
    selected = {}
    for signal in signals:
        for source in retrieve(records, signal["symbol"]):
            selected[source["source_id"]] = source
    evidence = list(selected.values())
    notes = None
    if use_llm:
        from agents import generate_notes
        notes = generate_notes(signals, evidence)
    report = {"as_of": as_of, "mode": "agents" if use_llm else "deterministic",
              "signals": signals, "sources": evidence, "agent_notes": notes,
              "methodology": {"daily_observations": 1, "weekly_observations": 5,
                              "monthly_observations": 21, "momentum_weights": [0.4, 0.4, 0.2],
                              "allocation": "illustrative equal weighting; no optimization"},
              "limitations": ["No trained ML model or backtest.",
                              "Lexical retrieval; source presence does not prove a claim.",
                              "Model interpretations require human review."]}
    report["checks"] = evaluate_report(report)
    if not report["checks"]["passed"]:
        raise ValueError("Report integrity checks failed")
    return report


def evaluate_report(report):
    signals = report.get("signals") or []
    symbols = [row["symbol"] for row in signals]
    issues = []
    if not signals or len(symbols) != len(set(symbols)):
        issues.append("Missing signals or duplicate tickers")
    if abs(sum(row["weight_pct"] for row in signals) - 100) > 0.00001:
        issues.append("Illustrative weights do not sum to 100")
    for row in signals:
        expected = round(0.4 * row["daily_pct"] + 0.4 * row["weekly_pct"] + 0.2 * row["monthly_pct"], 2)
        if abs(expected - row["momentum_score"]) > 0.02:
            issues.append("Momentum does not match component returns")
        if row["last_close"] <= 0 or not 0 < row["weight_pct"] <= 100:
            issues.append("Invalid price or weight")
        if row["price_date"] > report["as_of"]:
            issues.append("Future price in snapshot")
        for key in ("last_close", "daily_pct", "weekly_pct", "monthly_pct", "momentum_score", "weight_pct"):
            if not math.isfinite(row[key]):
                issues.append("Non-finite calculation")
    if any(source["published_at"] > report["as_of"] for source in report["sources"]):
        issues.append("Future document in snapshot")
    if report.get("agent_notes") is not None:
        from agents import validate_notes
        try:
            validate_notes(report["agent_notes"], signals, report["sources"])
        except ValueError as exc:
            issues.append(str(exc))
    return {"passed": not issues, "issues": issues,
            "scope": "structure, numeric validity, dates and citation support; not investment performance"}


def render_markdown(report):
    def safe(value):
        return str(value).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
    lines = ["# Financial Research Snapshot", "", "As of: " + report["as_of"],
             "Mode: " + report["mode"], "",
             "## Calculated observations", "",
             "| Ticker | Last price | Price date | 1 obs % | 5 obs % | 21 obs % | Momentum | Example weight % |",
             "|---|---:|---|---:|---:|---:|---:|---:|"]
    for row in report["signals"]:
        lines.append("| " + " | ".join(safe(row[key]) for key in
            ("symbol", "last_close", "price_date", "daily_pct", "weekly_pct", "monthly_pct",
             "momentum_score", "weight_pct")) + " |")
    lines += ["", "Momentum = 0.4 × 1-observation return + 0.4 × 5-observation return + "
              "0.2 × 21-observation return. Weights are an equal-weight illustration.", "",
              "## Document evidence", ""]
    if not report["sources"]:
        lines.append("No relevant document evidence available. No risk level is inferred.")
    for source in report["sources"]:
        lines += [f"### {safe(source['source_id'])}", "",
                  f"Ticker: {safe(source['ticker'])}; published: {source['published_at']}; "
                  f"page: {source['page'] or 'text'}.", "",
                  "> " + safe(source["text"]).replace("\n", "\n> "), ""]
    if report["agent_notes"] is not None:
        lines += ["## Optional model interpretation — review required", ""]
        for note in report["agent_notes"]["notes"]:
            lines += [f"### {safe(note['symbol'])}", "", safe(note["summary"]), ""]
            for citation in note["citations"]:
                lines.append(f"- [{safe(citation['source_id'])}] {safe(citation['quote'])}")
    lines += ["", "## Integrity checks", "", json.dumps(report["checks"]), "",
              "## Limits", "", *["- " + item for item in report["limitations"]]]
    return "\n".join(lines) + "\n"


def save_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(render_markdown(report), encoding="utf-8")
    with (output / "signals.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report["signals"][0]))
        writer.writeheader()
        writer.writerows(report["signals"])
    from report_chart import plot_signals
    plot_signals(report["signals"], output / "momentum.svg")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Use the included synthetic historical snapshot")
    parser.add_argument("--csv", type=Path, help="CSV with Symbol/Ticker, Date and Close/Adj Close")
    parser.add_argument("--symbols", nargs="+", help="Tickers to analyze")
    parser.add_argument("--as-of", help="Inclusive ISO date, e.g. 2025-02-11")
    parser.add_argument("--reports", type=Path, help="Directory containing index.json and source reports")
    parser.add_argument("--output-dir", type=Path, default=BASE / "output")
    parser.add_argument("--llm", action="store_true", help="Explicitly enable optional Qwen/CrewAI calls")
    args = parser.parse_args(argv)
    csv_path = args.csv or (BASE / "demo/prices.csv" if args.demo else None)
    symbols = args.symbols or (["ALPHA", "BETA"] if args.demo else None)
    as_of = args.as_of or ("2025-02-11" if args.demo else None)
    reports = args.reports or (BASE / "demo/reports" if args.demo else None)
    if not csv_path or not symbols or not as_of:
        parser.error("Use --demo or supply --csv, --symbols and --as-of")
    try:
        if args.llm:
            from dotenv import load_dotenv
            load_dotenv(BASE / ".env")
        report = build_report(csv_path, symbols, as_of, reports, args.llm)
        output = save_report(report, args.output_dir)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, ImportError) as exc:
        parser.exit(1, f"Research failed: {exc}\n")
    print(f"Report written to {output / 'report.md'}")
    print("Integrity checks:", json.dumps(report["checks"]))


if __name__ == "__main__":
    main()
