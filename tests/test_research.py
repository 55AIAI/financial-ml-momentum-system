import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from agents import validate_notes
from evidence import load_evidence, retrieve
from finance_mcp import compute_short_term_signals, handle_call
from main import BASE, build_report, evaluate_report


class Prices(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "prices.csv"

    def write(self, rows, fields=("Symbol", "Date", "Close")):
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(fields)
            writer.writerows(rows)

    def rows(self, symbol="A", count=22):
        return [[symbol, (date(2025, 1, 1) + timedelta(days=i)).isoformat(), 100 + i] for i in range(count)]

    def test_known_returns(self):
        self.write(self.rows())
        signal = compute_short_term_signals(["A"], self.path, "2025-01-22")[0]
        self.assertEqual((signal["daily_pct"], signal["weekly_pct"], signal["monthly_pct"]), (0.83, 4.31, 21.0))
        self.assertEqual(signal["momentum_score"], 6.26)

    def test_future_price_excluded(self):
        self.write(self.rows() + [["A", "2026-01-01", 999999]])
        self.assertEqual(compute_short_term_signals(["A"], self.path, "2025-01-22")[0]["last_close"], 121)

    def test_unsorted_input_is_sorted(self):
        self.write(list(reversed(self.rows())))
        self.assertEqual(compute_short_term_signals(["A"], self.path)[0]["last_close"], 121)

    def test_duplicate_dates_rejected(self):
        self.write(self.rows() + [self.rows()[0]])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            compute_short_term_signals(["A"], self.path)

    def test_invalid_prices_rejected(self):
        for price in (0, -1, "NaN", "inf", "invalid"):
            with self.subTest(price=price):
                rows = self.rows()
                rows[-1][-1] = price
                self.write(rows)
                with self.assertRaises(ValueError):
                    compute_short_term_signals(["A"], self.path)

    def test_missing_and_short_histories_rejected(self):
        self.write(self.rows(count=21))
        for symbols in (["A"], ["MISSING"], []):
            with self.subTest(symbols=symbols), self.assertRaises(ValueError):
                compute_short_term_signals(symbols, self.path)

    def test_adjusted_close_preferred(self):
        self.write([row + [2 * row[-1]] for row in self.rows()],
                   ("Symbol", "Date", "Close", "Adj Close"))
        signal = compute_short_term_signals(["A"], self.path)[0]
        self.assertEqual(signal["last_close"], 242)
        self.assertEqual(signal["price_field"], "Adj Close")

    def test_equal_weights_sum_to_100(self):
        self.write(self.rows("A") + self.rows("B") + self.rows("C"))
        signals = compute_short_term_signals(["A", "B", "C", "A"], self.path)
        self.assertEqual(len(signals), 3)
        self.assertEqual(sum(row["weight_pct"] for row in signals), 100)

    def test_rpc_calculates_real_signals(self):
        self.write(self.rows())
        result = handle_call({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                              "params": {"name": "get_short_term_signals",
                                         "arguments": {"symbols": ["A"], "csv_path": str(self.path)}}})
        self.assertEqual(result["id"], 7)
        self.assertEqual(json.loads(result["result"]["content"][0]["text"])[0]["last_close"], 121)


class Evidence(unittest.TestCase):
    def setUp(self):
        self.records = load_evidence(BASE / "demo/reports", "2025-02-11")

    def test_future_document_excluded(self):
        self.assertNotIn("future.txt", [r["filename"] for r in self.records])

    def test_ticker_filter(self):
        result = retrieve(self.records, "BETA", "business risk revenue")
        self.assertTrue(result)
        self.assertEqual({r["ticker"] for r in result}, {"BETA"})

    def test_no_match_is_empty(self):
        self.assertEqual(retrieve(self.records, "ALPHA", "unrelatedzzzz"), [])

    def test_source_metadata_preserved(self):
        source = retrieve(self.records, "ALPHA")[0]
        self.assertEqual(source["published_at"], "2025-01-15")
        self.assertEqual(source["source_id"], "alpha.txt:0:0")
        self.assertIsNone(source["page"])

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "index.json").write_text(json.dumps([
                {"filename": "../outside.txt", "ticker": "A", "published_at": "2025-01-01"}]))
            with self.assertRaisesRegex(ValueError, "inside"):
                load_evidence(root, "2025-02-11")

    def test_missing_date_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "index.json").write_text('[{"filename":"a.txt","ticker":"A"}]')
            with self.assertRaises(KeyError):
                load_evidence(root, "2025-02-11")


class AgentValidation(unittest.TestCase):
    def setUp(self):
        self.report = build_report(BASE / "demo/prices.csv", ["ALPHA", "BETA"], "2025-02-11",
                                   BASE / "demo/reports")
        self.source = next(r for r in self.report["sources"] if r["ticker"] == "ALPHA")
        self.note = {"notes": [{"symbol": "ALPHA", "summary": "A single supplier is an operational risk.",
                               "citations": [{"source_id": self.source["source_id"],
                                              "quote": "The business risk is a single component supplier."}]}]}

    def check(self, payload):
        return validate_notes(payload, self.report["signals"], self.report["sources"])

    def test_exact_quote_accepted(self):
        self.assertEqual(self.check(self.note)["notes"][0]["symbol"], "ALPHA")

    def test_fabricated_quote_rejected(self):
        self.note["notes"][0]["citations"][0]["quote"] = "Revenue grew by 900 percent."
        with self.assertRaisesRegex(ValueError, "quote"):
            self.check(self.note)

    def test_other_ticker_citation_rejected(self):
        self.note["notes"][0]["symbol"] = "BETA"
        with self.assertRaisesRegex(ValueError, "another ticker"):
            self.check(self.note)

    def test_invented_numbers_rejected(self):
        self.note["notes"][0]["summary"] = "Revenue growth will be 900 percent."
        with self.assertRaisesRegex(ValueError, "numbers"):
            self.check(self.note)

    def test_wrong_return_sign_rejected(self):
        self.note["notes"][0]["summary"] = "The monthly return was -19.44 percent."
        with self.assertRaisesRegex(ValueError, "numbers"):
            self.check(self.note)

    def test_unknown_source_rejected(self):
        self.note["notes"][0]["citations"][0]["source_id"] = "invented"
        with self.assertRaisesRegex(ValueError, "Unknown source"):
            self.check(self.note)

    def test_empty_evidence_has_no_notes(self):
        from agents import generate_notes
        with patch.dict(os.environ, {"QWEN_API_KEY": "test-not-a-real-key"}):
            with self.assertRaisesRegex(ValueError, "evidence"):
                generate_notes(self.report["signals"], [])

    def test_crew_chain_contract_without_network(self):
        from types import SimpleNamespace
        from agents import generate_notes
        objects = []
        class Item:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                objects.append(self)
        note = self.note
        class Crew(Item):
            def kickoff(self):
                return SimpleNamespace(pydantic=None, raw=json.dumps(note))
        module = SimpleNamespace(Agent=Item, Task=Item, LLM=Item, Crew=Crew)
        with patch.dict(sys.modules, {"crewai": module}), patch.dict(os.environ, {"QWEN_API_KEY": "test-not-a-real-key"}):
            result = generate_notes(self.report["signals"], self.report["sources"])
        self.assertTrue(result["notes"])
        crew = objects[-1].kwargs
        self.assertEqual(len(crew["agents"]), 2)
        self.assertEqual(crew["tasks"][1].kwargs["context"], [crew["tasks"][0]])


class ReportTests(unittest.TestCase):
    def report(self):
        return build_report(BASE / "demo/prices.csv", ["ALPHA", "BETA"], "2025-02-11", BASE / "demo/reports")

    def test_offline_snapshot_is_reproducible(self):
        self.assertEqual(self.report(), self.report())
        self.assertTrue(self.report()["checks"]["passed"])

    def test_tampered_momentum_fails(self):
        report = self.report()
        report["signals"][0]["momentum_score"] += 10
        self.assertFalse(evaluate_report(report)["passed"])

    def test_future_source_fails(self):
        report = self.report()
        report["sources"][0]["published_at"] = "2030-01-01"
        self.assertFalse(evaluate_report(report)["passed"])

    def test_missing_sources_do_not_create_risk_claims(self):
        report = build_report(BASE / "demo/prices.csv", ["ALPHA"], "2025-02-11")
        from main import render_markdown
        self.assertIn("No relevant document evidence", render_markdown(report))
        self.assertEqual(report["sources"], [])

    def test_cli_demo_without_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {k: v for k, v in os.environ.items() if k not in {"QWEN_API_KEY", "OPENAI_API_KEY"}}
            result = subprocess.run([sys.executable, "-B", str(BASE / "main.py"), "--demo",
                                     "--output-dir", folder], env=env, capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((Path(folder) / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["checks"]["passed"])
            self.assertTrue((Path(folder) / "report.md").exists())
            self.assertTrue((Path(folder) / "signals.csv").exists())
            self.assertTrue((Path(folder) / "momentum.svg").exists())
