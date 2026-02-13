import sys
import os
import json
import traceback
from typing import Dict, Any, List

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
MARKET = os.path.join(DATA, "market")
CSV_PATH = os.path.join(MARKET, "sp500_prices_2014_2017.csv")


# ---------- helpers ----------

def _detect_col(df: pd.DataFrame, candidates: List[str]) -> str:
    lower_map = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    raise KeyError(f"None of {candidates} found in columns {list(df.columns)}")


def compute_short_term_signals(symbols: List[str]) -> List[Dict[str, Any]]:
    df = pd.read_csv(CSV_PATH)

    sym_col = _detect_col(df, ["Symbol", "symbol", "Ticker"])
    date_col = _detect_col(df, ["Date", "date"])
    close_col = _detect_col(df, ["Close", "Adj Close", "close"])

    df[date_col] = pd.to_datetime(df[date_col])
    df = df[df[sym_col].isin(symbols)].copy()
    df.sort_values([sym_col, date_col], inplace=True)

    records: List[Dict[str, Any]] = []

    for sym, g in df.groupby(sym_col):
        g = g.sort_values(date_col)
        closes = g[close_col].values

        if len(closes) < 22:
            # Not enough history
            continue

        last = closes[-1]
        prev1 = closes[-2]
        prev5 = closes[-6] if len(closes) >= 6 else closes[0]
        prev21 = closes[-22] if len(closes) >= 22 else closes[0]

        daily_pct = (last / prev1 - 1.0) * 100.0
        weekly_pct = (last / prev5 - 1.0) * 100.0
        monthly_pct = (last / prev21 - 1.0) * 100.0

        # Simple momentum score: heavier on daily + weekly
        momentum_score = daily_pct * 0.4 + weekly_pct * 0.4 + monthly_pct * 0.2

        records.append(
            {
                "symbol": sym,
                "daily_pct": round(float(daily_pct), 2),
                "weekly_pct": round(float(weekly_pct), 2),
                "monthly_pct": round(float(monthly_pct), 2),
                "momentum_score": round(float(momentum_score), 2),
            }
        )

    # sort and equal weights
    records.sort(key=lambda r: r["momentum_score"], reverse=True)
    n = len(records) or 1
    for r in records:
        r["weight_pct"] = round(100.0 / n, 2)

    return records


# ---------- MCP handler ----------

def handle_call(req: Dict[str, Any]) -> Dict[str, Any]:
    name = req.get("params", {}).get("name")
    args = req.get("params", {}).get("arguments", {})

    try:
        if name == "get_short_term_signals":
            symbols = args.get("symbols") or []
            if not isinstance(symbols, list):
                raise ValueError("symbols must be a list of tickers")
            res = compute_short_term_signals([str(s) for s in symbols])
        else:
            return {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }

        return {
            "jsonrpc": "2.0",
            "id": req.get("id"),
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(res, ensure_ascii=False)}
                ]
            },
        }

    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": req.get("id"),
            "error": {
                "code": -32000,
                "message": "Internal error in finance_mcp",
                "details": traceback.format_exc(),
            },
        }


def main():
    try:
        line = sys.stdin.readline()
        if not line:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": "Empty input to MCP server",
                        },
                    },
                    ensure_ascii=False,
                )
            )
            return

        req = json.loads(line)
        resp = handle_call(req)
        print(json.dumps(resp, ensure_ascii=False))

    except Exception:
        err = traceback.format_exc()
        print(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32000,
                        "message": "Fatal server crash in finance_mcp",
                        "details": err,
                        },
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
