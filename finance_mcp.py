"""Deterministic price calculations and a small local JSON-RPC compatibility CLI."""
import csv
import math
import os
from datetime import date
from itertools import pairwise
from pathlib import Path
from statistics import stdev

from inputs import iso_date, ticker
from local_rpc import dispatch, serve

CSV_PATH = Path(__file__).parent / "data/market/sp500_prices_2014_2017.csv"


def _column(fieldnames, aliases):
    if not fieldnames or any(not name or not name.strip() for name in fieldnames):
        raise ValueError("CSV header must contain nonempty column names")
    normalized = [name.strip().casefold() for name in fieldnames]
    if len(normalized) != len(set(normalized)):
        raise ValueError("CSV header contains duplicate column names")
    names = dict(zip(normalized, fieldnames))
    for alias in aliases:
        if alias.casefold() in names:
            return names[alias.casefold()]
    raise ValueError("Missing CSV column: " + " / ".join(aliases))


def compute_short_term_signals(symbols, csv_path=None, as_of=None):
    """Use only prices known on as_of; horizons count observations, not calendar days."""
    if not isinstance(symbols, (list, tuple)) or not symbols:
        raise ValueError("symbols must be a nonempty list of ticker strings")
    symbols = list(dict.fromkeys(ticker(value) for value in symbols))
    cutoff = iso_date(as_of, "as_of") if as_of is not None else date.max
    rows = {symbol: [] for symbol in symbols}
    seen = set()
    with Path(csv_path or os.getenv("MARKET_CSV", CSV_PATH)).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        symbol_col = _column(reader.fieldnames, ("Symbol", "Ticker"))
        date_col = _column(reader.fieldnames, ("Date",))
        close_col = _column(reader.fieldnames, ("Adj Close", "Close"))
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Invalid CSV row {line}: cell count does not match header")
            symbol = (row[symbol_col] or "").strip().upper()
            if symbol not in rows:
                continue
            try:
                observed = iso_date((row[date_col] or "").strip(), "Date")
                if observed > cutoff:
                    continue
                close = float(row[close_col])
                if not math.isfinite(close) or close <= 0:
                    raise ValueError("price must be positive and finite")
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid price row {line} for {symbol}: {exc}") from exc
            key = symbol, observed
            if key in seen:
                raise ValueError(f"Duplicate ticker/date at row {line}: {symbol} {observed}")
            seen.add(key)
            rows[symbol].append((observed, close))
    result = []
    for symbol, observations in rows.items():
        observations.sort()
        if len(observations) < 22:
            raise ValueError(f"{symbol} needs 22 price observations on or before {cutoff}; got {len(observations)}")
        last = observations[-1][1]
        daily, weekly, monthly = [
            (last / observations[-offset][1] - 1) * 100 for offset in (2, 6, 22)
        ]
        window = observations[-22:]
        returns = [current[1] / previous[1] - 1
                   for previous, current in pairwise(window)]
        if not all(math.isfinite(value) for value in [daily, weekly, monthly, *returns]):
            raise ValueError(f"Non-finite derived return for {symbol}")
        volatility = stdev(returns) * math.sqrt(252) * 100
        if not math.isfinite(volatility):
            raise ValueError(f"Non-finite volatility for {symbol}")
        peak = window[0][1]
        drawdown = 0.0
        for _, price in window:
            peak = max(peak, price)
            drawdown = max(drawdown, (1 - price / peak) * 100)
        result.append({
            "symbol": symbol, "price_date": observations[-1][0].isoformat(),
            "last_close": last, "price_field": close_col,
            "daily_pct": round(daily, 2), "weekly_pct": round(weekly, 2),
            "monthly_pct": round(monthly, 2),
            "momentum_score": round(daily * 0.4 + weekly * 0.4 + monthly * 0.2, 2),
            "observation_count": len(observations),
            "risk_window_start": window[0][0].isoformat(),
            "risk_max_gap_days": max((current[0] - previous[0]).days
                                     for previous, current in pairwise(window)),
            "volatility_21_annualized_pct": round(volatility, 2),
            "max_drawdown_21_pct": round(drawdown, 2),
        })
    result.sort(key=lambda row: (-row["momentum_score"], row["symbol"]))
    # Integer basis points keep the displayed allocation sum exactly at 100%.
    weight, remainder = divmod(10000, len(result))
    for index, row in enumerate(result):
        row["weight_pct"] = (weight + (index < remainder)) / 100
    return result


def handle_call(request):
    return dispatch(request, {
        "get_short_term_signals": lambda args: compute_short_term_signals(
            args["symbols"], args.get("csv_path"), args.get("as_of")),
    })


if __name__ == "__main__":
    serve(handle_call)
