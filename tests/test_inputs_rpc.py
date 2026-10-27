import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evidence import load_evidence, retrieve
from finance_mcp import compute_short_term_signals, handle_call as finance_call
from main import BASE
from pdf_mcp import handle_call as evidence_call


class InputValidation(unittest.TestCase):
    def test_symbols_require_strings_in_a_list(self):
        for value in ("ALPHA", None, 1, [None], [5], [""], ["ALPHA", " "]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compute_short_term_signals(value, BASE / "demo/prices.csv", "2025-02-11")

    def test_dates_use_the_documented_iso_form(self):
        for value in ("20250211", "2025-W07-2", 20250211, "", "2025-02-30"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compute_short_term_signals(["ALPHA"], BASE / "demo/prices.csv", value)

    def test_ambiguous_headers_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prices.csv"
            for fields in (["Symbol", "Date", "Close", " close "], ["Symbol", "Date", ""]):
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(fields)
                    writer.writerow(["ALPHA", "2025-01-01", 100, 900][:len(fields)])
                with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, "header"):
                    compute_short_term_signals(["ALPHA"], path)

    def test_wrong_csv_row_width_reports_line_number(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prices.csv"
            for row in ("ALPHA,2025-01-01", "ALPHA,2025-01-01,100,extra"):
                path.write_text("Symbol,Date,Close\n" + row + "\n", encoding="utf-8")
                with self.subTest(row=row), self.assertRaisesRegex(ValueError, "row 2"):
                    compute_short_term_signals(["ALPHA"], path)

    def test_evidence_requires_text_ticker_and_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "report.txt").write_text("Business risk and revenue.", encoding="utf-8")
            for field in ("ticker", "filename"):
                for value in (None, 42, " "):
                    entry = {"filename": "report.txt", "ticker": "ALPHA", "published_at": "2025-01-01"}
                    entry[field] = value
                    (root / "index.json").write_text(json.dumps([entry]), encoding="utf-8")
                    with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                        load_evidence(root, "2025-02-11")

    def test_evidence_dates_use_iso_form(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "index.json").write_text(json.dumps([
                {"filename": "missing.txt", "ticker": "A", "published_at": "20250101"}]))
            with self.assertRaisesRegex(ValueError, "published_at"):
                load_evidence(root, "2025-02-11")

    def test_aliases_cannot_duplicate_an_evidence_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "report.txt").write_text("Business risk and revenue.")
            (root / "index.json").write_text(json.dumps([
                {"filename": name, "ticker": "A", "published_at": "2025-01-01"}
                for name in ("report.txt", "./report.txt")]))
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_evidence(root, "2025-02-11")

    def test_invalid_pdf_has_a_clear_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "broken.pdf").write_bytes(b"not a pdf")
            (root / "index.json").write_text(json.dumps([
                {"filename": "broken.pdf", "ticker": "A", "published_at": "2025-01-01"}]))
            with self.assertRaisesRegex(ValueError, "PDF"):
                load_evidence(root, "2025-02-11")

    def test_retrieval_rejects_invalid_argument_types(self):
        for query, ticker, limit in ((None, "A", 3), ("risk", None, 3), ("risk", "A", True),
                                      ("risk", "A", 2.5), ("risk", " ", 3)):
            with self.subTest(query=query, ticker=ticker, limit=limit), self.assertRaises(ValueError):
                retrieve([], ticker, query, limit)


    def test_encrypted_pdf_is_rejected_explicitly(self):
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.encrypt("synthetic-test-password")
            writer.write(root / "encrypted.pdf")
            (root / "index.json").write_text(json.dumps([
                {"filename": "encrypted.pdf", "ticker": "A", "published_at": "2025-01-01"}]))
            with self.assertRaisesRegex(ValueError, "Encrypted PDF"):
                load_evidence(root, "2025-02-11")

    def test_cli_validation_error_has_no_traceback(self):
        result = subprocess.run([sys.executable, str(BASE / "main.py"), "--demo",
                                 "--as-of", "20250211"], check=False, capture_output=True,
                                text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertIn("YYYY-MM-DD", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class LocalToolProtocol(unittest.TestCase):
    def request(self, **changes):
        value = {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "get_short_term_signals", "arguments": {
                     "symbols": ["ALPHA"], "csv_path": str(BASE / "demo/prices.csv"),
                     "as_of": "2025-02-11"}}}
        value.update(changes)
        return value

    def test_invalid_requests_return_errors_instead_of_crashing(self):
        for handler in (finance_call, evidence_call):
            for request in (None, [], 5, {}, self.request(jsonrpc="1.0"),
                            self.request(id=True), self.request(method=[])):
                with self.subTest(handler=handler.__module__, request=request):
                    result = handler(request)
                    self.assertEqual(result["error"]["code"], -32600)

    def test_invalid_params_return_invalid_params_error(self):
        for handler in (finance_call, evidence_call):
            for params in (None, [], {"name": None}, {"name": "unknown"},
                           {"name": "get_short_term_signals", "arguments": []}):
                with self.subTest(handler=handler.__module__, params=params):
                    result = handler(self.request(params=params))
                    self.assertEqual(result["error"]["code"], -32602)

    def test_unknown_method_returns_method_not_found(self):
        result = finance_call(self.request(method="initialize"))
        self.assertEqual(result["error"]["code"], -32601)

    def test_notifications_have_no_response(self):
        request = self.request()
        del request["id"]
        self.assertIsNone(finance_call(request))
        request["params"] = {}
        self.assertIsNone(finance_call(request))

    def test_null_id_is_a_request_and_is_echoed(self):
        result = finance_call(self.request(id=None))
        self.assertIsNone(result["id"])
        self.assertIn("result", result)

    def test_stream_continues_after_bad_json_and_accepts_multiple_requests(self):
        requests = ["{bad json", json.dumps(self.request(id="first")),
                    json.dumps({**self.request(), "id": "second"})]
        result = subprocess.run([sys.executable, str(BASE / "finance_mcp.py")],
                                input="\n".join(requests) + "\n", capture_output=True,
                                text=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses), 3)
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual([row["id"] for row in responses[1:]], ["first", "second"])
        self.assertTrue(all("result" in row for row in responses[1:]))

    def test_internal_error_does_not_stop_the_stream(self):
        from local_rpc import dispatch, serve

        def broken(_):
            raise RuntimeError("private implementation detail")

        requests = [self.request(params={"name": "broken"}),
                    self.request(id=4, params={"name": "ok"})]
        output = io.StringIO()
        serve(lambda request: dispatch(request, {"broken": broken, "ok": lambda _: {"ok": True}}),
              io.StringIO("\n".join(json.dumps(item) for item in requests)), output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(responses[0]["error"]["code"], -32603)
        self.assertNotIn("private implementation detail", output.getvalue())
        self.assertIn("result", responses[1])

    def test_pdf_stream_suppresses_notifications_and_continues(self):
        request = self.request(params={"name": "get_global_risk", "arguments": {
            "ticker": "ALPHA", "as_of": "2025-02-11",
            "reports_dir": str(BASE / "demo/reports")}})
        notification = dict(request)
        del notification["id"]
        result = subprocess.run([sys.executable, str(BASE / "pdf_mcp.py")],
                                input=json.dumps(notification) + "\n" + json.dumps(request) + "\n",
                                check=False, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["id"], request["id"])
        risk = json.loads(responses[0]["result"]["content"][0]["text"])
        self.assertEqual(risk["risk_level"], "Unassessed")

    def test_evidence_tool_returns_scoped_results(self):
        request = self.request(params={"name": "rag_search_risk", "arguments": {
            "query": "business risk", "ticker": "ALPHA", "as_of": "2025-02-11",
            "reports_dir": str(BASE / "demo/reports")}})
        response = evidence_call(request)
        records = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(records)
        self.assertEqual({row["ticker"] for row in records}, {"ALPHA"})


if __name__ == "__main__":
    unittest.main()
