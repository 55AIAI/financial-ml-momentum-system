import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from finance_mcp import compute_short_term_signals
from main import BASE, assess_data_quality, build_report, evaluate_report, render_markdown


class RiskMetrics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.csv = Path(self.temp.name) / "prices.csv"

    def write_prices(self, prices, symbol="A", spacing=1):
        with self.csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Symbol", "Date", "Close"])
            writer.writerows([symbol, (date(2025, 1, 1) + timedelta(days=i * spacing)).isoformat(), price]
                             for i, price in enumerate(prices))

    def signal(self, prices):
        self.write_prices(prices)
        return compute_short_term_signals(["A"], self.csv)[0]

    def test_flat_prices_have_no_volatility_or_drawdown(self):
        signal = self.signal([100] * 22)
        self.assertEqual(signal["volatility_21_annualized_pct"], 0)
        self.assertEqual(signal["max_drawdown_21_pct"], 0)
        self.assertEqual(signal["risk_window_start"], "2025-01-01")

    def test_known_risk_path(self):
        # 21 simple returns: +100%, -50%, then 19 zeros.
        # Sample variance = (sum(x*x) - sum(x)^2 / n) / (n - 1).
        signal = self.signal([100, 200] + [100] * 20)
        reference = math.sqrt((1.25 - 0.25 / 21) / 20) * math.sqrt(252) * 100
        self.assertEqual(signal["volatility_21_annualized_pct"], round(reference, 2))
        self.assertEqual(signal["max_drawdown_21_pct"], 50)

    def test_risk_window_excludes_older_crash(self):
        signal = self.signal([1000, 100] + [100] * 22)
        self.assertEqual(signal["max_drawdown_21_pct"], 0)
        self.assertEqual(signal["volatility_21_annualized_pct"], 0)
        self.assertEqual(signal["risk_window_start"], "2025-01-03")

    def test_risk_metrics_do_not_depend_on_price_scale(self):
        first = self.signal([100, 200] + [100] * 20)
        second = self.signal([1, 2] + [1] * 20)
        for key in ("volatility_21_annualized_pct", "max_drawdown_21_pct"):
            self.assertEqual(first[key], second[key])

    def test_future_crash_does_not_change_historical_risk(self):
        self.write_prices([100] * 22 + [1])
        signal = compute_short_term_signals(["A"], self.csv, "2025-01-22")[0]
        self.assertEqual(signal["max_drawdown_21_pct"], 0)
        self.assertEqual(signal["volatility_21_annualized_pct"], 0)

    def test_finite_prices_with_overflowing_returns_are_rejected(self):
        self.write_prices([1e-300] * 21 + [1e300])
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            compute_short_term_signals(["A"], self.csv)

    def test_sparse_series_warns_about_annualization(self):
        self.write_prices([100] * 22, spacing=30)
        signal = compute_short_term_signals(["A"], self.csv)[0]
        quality = assess_data_quality([signal], signal["price_date"])
        self.assertEqual(signal["risk_max_gap_days"], 30)
        self.assertIn("SPARSE_PRICE_WINDOW", {item["code"] for item in quality["warnings"]})


class DataQuality(unittest.TestCase):
    def report(self, as_of="2025-02-11", **kwargs):
        return build_report(BASE / "demo/prices.csv", ["ALPHA", "BETA"], as_of,
                            BASE / "demo/reports", **kwargs)

    def test_aligned_demo_has_no_warnings(self):
        self.assertEqual(self.report()["data_quality"]["warnings"], [])
        self.assertEqual(self.report()["data_quality"]["price_age_days"], {"ALPHA": 0, "BETA": 0})

    def test_stale_prices_warn_without_failing_integrity(self):
        report = self.report("2025-02-20")
        self.assertTrue(report["checks"]["passed"])
        self.assertEqual([w["code"] for w in report["data_quality"]["warnings"]],
                         ["STALE_PRICE", "STALE_PRICE"])
        self.assertEqual(report["data_quality"]["price_age_days"]["ALPHA"], 9)

    def test_age_threshold_is_inclusive_and_configurable(self):
        self.assertFalse(self.report("2025-02-18")["data_quality"]["warnings"])
        self.assertTrue(self.report("2025-02-18", max_price_age_days=6)["data_quality"]["warnings"])

    def test_mixed_dates_are_explicit(self):
        signals = self.report()["signals"]
        signals[0]["price_date"] = "2025-02-10"
        quality = assess_data_quality(signals, "2025-02-11")
        self.assertEqual([w["code"] for w in quality["warnings"]], ["MIXED_PRICE_DATES"])
        self.assertEqual(quality["price_age_days"][signals[0]["symbol"]], 1)

    def test_invalid_threshold_is_rejected_before_agents(self):
        with patch("agents.generate_notes") as generate:
            for value in (-1, True, 1.5, "7"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self.report(use_llm=True, max_price_age_days=value)
            generate.assert_not_called()

    def test_future_price_is_rejected(self):
        signals = self.report()["signals"]
        with self.assertRaisesRegex(ValueError, "Future"):
            assess_data_quality(signals, "2025-01-01")

    def test_tampered_risk_values_fail_integrity(self):
        for key, value in (("max_drawdown_21_pct", -1), ("max_drawdown_21_pct", 101),
                           ("volatility_21_annualized_pct", -1),
                           ("volatility_21_annualized_pct", float("nan")),
                           ("max_drawdown_21_pct", float("inf"))):
            report = self.report()
            report["signals"][0][key] = value
            with self.subTest(key=key, value=value):
                self.assertFalse(evaluate_report(report)["passed"])

    def test_deleted_warning_fails_integrity(self):
        report = self.report("2025-02-20")
        report["data_quality"]["warnings"] = []
        self.assertFalse(evaluate_report(report)["passed"])

    def test_malformed_reports_fail_without_throwing(self):
        for value in ({}, {"as_of": "not-a-date"}, {"as_of": "2025-02-11", "signals": [{}]}):
            with self.subTest(value=value):
                self.assertFalse(evaluate_report(value)["passed"])

    def test_markdown_includes_risk_and_quality(self):
        text = render_markdown(self.report("2025-02-20"))
        for expected in ("Annualized volatility", "Max drawdown", "Window start", "STALE_PRICE"):
            self.assertIn(expected, text)

    def test_agents_receive_data_quality(self):
        with patch("agents.generate_notes", return_value={"notes": []}) as generate:
            report = self.report("2025-02-20", use_llm=True)
        self.assertEqual(generate.call_args.args[2], report["data_quality"])

    def test_agent_warning_numbers_are_scoped_to_the_ticker(self):
        from agents import validate_notes

        report = self.report()
        source = next(item for item in report["sources"] if item["ticker"] == "ALPHA")
        quality = {"price_age_days": {"ALPHA": 999, "BETA": 888}, "max_price_age_days": 7}
        note = {"notes": [{"symbol": "ALPHA", "summary": "Latest price is 999 days old; threshold is 7 days.",
                           "citations": [{"source_id": source["source_id"],
                                          "quote": "The business risk is a single component supplier."}]}]}
        self.assertTrue(validate_notes(note, report["signals"], report["sources"], quality)["notes"])
        note["notes"][0]["summary"] = "Latest price is 888 days old."
        with self.assertRaisesRegex(ValueError, "unsupported numbers"):
            validate_notes(note, report["signals"], report["sources"], quality)

    def test_cli_reports_staleness_and_exports_risk(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, str(BASE / "main.py"), "--demo",
                                     "--as-of", "2025-02-20", "--output-dir", folder],
                                    check=False, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("STALE_PRICE", result.stdout)
            report = json.loads((Path(folder) / "report.json").read_text(encoding="utf-8"))
            self.assertIn("max_drawdown_21_pct", report["signals"][0])
            with (Path(folder) / "signals.csv").open(encoding="utf-8", newline="") as handle:
                self.assertIn("volatility_21_annualized_pct", csv.DictReader(handle).fieldnames)


if __name__ == "__main__":
    unittest.main()
