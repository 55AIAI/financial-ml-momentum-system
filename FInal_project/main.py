import os
import json
import time
import logging
import subprocess
from datetime import datetime
from typing import List, Dict, Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from crewai import Agent, Crew, Task, Process

# =========================================================
# 0. ENV, PATHS, LOGGING
# =========================================================

load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
MARKET = os.path.join(DATA, "market")
OUT = os.path.join(DATA, "output")
DBG = os.path.join(DATA, "debug")
MEM_PATH = os.path.join(DATA, "long_memory.json")
LOG_PATH = os.path.join(DATA, "system.log")

os.makedirs(OUT, exist_ok=True)
os.makedirs(DBG, exist_ok=True)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Make CrewAI use Qwen (DashScope compatible OpenAI endpoint)
os.environ["OPENAI_API_KEY"] = os.getenv("DASHSCOPE_API_KEY", "")
os.environ["OPENAI_BASE_URL"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"


# =========================================================
# 1. MCP CLIENT HELPER
# =========================================================

def call_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """
    Call an MCP tool via subprocess (STDIN/STDOUT JSON-RPC).
    Very defensive: ignores any non-JSON lines (like stray ANSI codes).
    """
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    if tool_name == "get_short_term_signals":
        server_script = "finance_mcp.py"
    elif tool_name in ("get_global_risk", "rag_search_risk"):
        server_script = "pdf_mcp.py"
    else:
        raise ValueError(f"Unknown MCP tool: {tool_name}")

    proc = subprocess.run(
        ["python", server_script],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        cwd=BASE,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"MCP server error ({server_script}): {proc.stderr}"
        )

    stdout = proc.stdout.strip()
    if not stdout:
        raise RuntimeError(f"Empty MCP response from {server_script}")

    # Find the LAST line that looks like JSON
    json_line = None
    for line in reversed(stdout.splitlines()):
        s = line.strip()
        if s.startswith("{") or s.startswith("["):
            json_line = s
            break

    if json_line is None:
        raise RuntimeError(
            f"Failed to find JSON in MCP output from {server_script}. Raw: {stdout!r}"
        )

    try:
        response = json.loads(json_line)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse MCP JSON: {e}\nRaw: {json_line}")

    if "error" in response:
        raise RuntimeError(f"MCP tool error: {response['error']}")

    result_obj = response.get("result", {})
    content_list = result_obj.get("content", [])
    if not content_list:
        return None

    text = content_list[0].get("text", "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


# =========================================================
# 2. UTILITIES / MEMORY
# =========================================================

def retry(func, max_attempts: int = 3, wait: float = 2.0):
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as e:
            logging.error(f"[retry] attempt {attempt} failed: {e}")
            time.sleep(wait)
    raise RuntimeError("Max retry attempts exceeded.")


def load_long_memory() -> List[Dict[str, Any]]:
    if not os.path.exists(MEM_PATH):
        return []
    try:
        with open(MEM_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_long_memory(entry: Dict[str, Any]):
    mem = load_long_memory()
    mem.append(entry)
    mem = mem[-10:]  # keep last 10 runs
    with open(MEM_PATH, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)


def df_to_markdown(df: pd.DataFrame) -> str:
    """Create markdown table WITHOUT requiring tabulate."""
    cols = list(df.columns)
    lines = []
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")
    for _, row in df.iterrows():
        vals = []
        for v in row:
            if isinstance(v, (int, float, np.number)):
                vals.append(f"{v:.2f}")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


# =========================================================
# 3. DATA HELPERS
# =========================================================

def _detect_col(df: pd.DataFrame, candidates: List[str]) -> str:
    lower_map = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    raise KeyError(f"None of {candidates} found in columns {list(df.columns)}")


def get_top10_symbols() -> List[str]:
    """Pick TOP-10 symbols by average close price."""
    path = os.path.join(MARKET, "sp500_prices_2014_2017.csv")
    df = pd.read_csv(path)

    sym_col = _detect_col(df, ["Symbol", "symbol", "Ticker"])
    date_col = _detect_col(df, ["Date", "date"])
    close_col = _detect_col(df, ["Close", "Adj Close", "close"])

    df[date_col] = pd.to_datetime(df[date_col])
    grouped = df.groupby(sym_col)[close_col].mean().sort_values(ascending=False)
    syms = grouped.head(10).index.tolist()
    print(f"Using TOP-10 symbols: {syms}")
    return syms


def build_short_term_signals(symbols: List[str]) -> pd.DataFrame:
    """Ask finance MCP to compute short-term metrics for the given symbols."""
    res = retry(lambda: call_mcp_tool("get_short_term_signals", {"symbols": symbols}))
    if not isinstance(res, list):
        raise RuntimeError(f"Unexpected MCP result for signals: {res}")

    df = pd.DataFrame(res)
    # Save signals CSV (with timestamp)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUT, f"signals_{ts}.csv")
    df.to_csv(path, index=False)
    print(f"Signals CSV: {path}")
    return df


def plot_momentum_chart(signals: pd.DataFrame) -> str:
    """Simple bar chart of momentum_score."""
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 5))
    x = signals["symbol"]
    y = signals["momentum_score"]
    plt.bar(x, y)
    plt.title("Short-Term Momentum Score (Top-10)")
    plt.xlabel("Symbol")
    plt.ylabel("Momentum Score")
    plt.tight_layout()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUT, f"momentum_chart_{ts}.png")
    plt.savefig(path)
    plt.close()
    return path


def get_global_risk() -> Dict[str, Any]:
    """Call pdf MCP to get global risk level and bullets."""
    res = retry(lambda: call_mcp_tool("get_global_risk", {}))
    if not isinstance(res, dict):
        raise RuntimeError(f"Unexpected MCP result for risk: {res}")
    return res


# =========================================================
# 4. CREW AGENTS & TASKS (Option A)
# =========================================================

def build_crew(signals_md: str, risk_info: Dict[str, Any]) -> Crew:
    risk_level = risk_info.get("risk_level", "Medium")
    risks = risk_info.get("risks", [])

    risks_text = ", ".join(risks) if isinstance(risks, list) else str(risks)

    momentum_agent = Agent(
        role="Momentum Analyst",
        goal="Analyze short-term price momentum for a small equity portfolio.",
        backstory="You specialize in daily and weekly price action and simple quantitative signals.",
        llm="gpt-4o-mini",  # alias for Qwen via OpenAI compatible endpoint
    )

    macro_agent = Agent(
        role="Macro Risk Analyst",
        goal="Explain the global macro risk environment for the next few months.",
        backstory="You focus on reading financial stability reports and macro risk factors.",
        llm="gpt-4o-mini",
    )

    portfolio_agent = Agent(
        role="Short-Term Portfolio Builder",
        goal="Build a short-term momentum portfolio using the given signals and macro risk.",
        backstory="You allocate weights based on momentum strength while respecting risk level.",
        llm="gpt-4o-mini",
    )

    writer_agent = Agent(
        role="Investment Writer",
        goal="Write a concise student-level memo summarizing the results.",
        backstory="You turn quantitative output into clear, structured markdown reports.",
        llm="gpt-4o-mini",
    )

    t_momentum = Task(
        description=f"""
Short-term movers table (daily/weekly/monthly %):

{signals_md}

Global macro risk level from PDFs: {risk_level}
Risks: {risks_text}

Task: Analyze which stocks show the strongest short-term upward movement.
Focus only on daily_pct and weekly_pct. Ignore long-term valuation or detailed fundamentals.
Output a markdown section titled 'Short-Term Momentum Analysis'.
""".strip(),
        agent=momentum_agent,
    )

    t_macro = Task(
        description=f"""
Global macro risk information extracted from financial PDFs:

Risk level: {risk_level}
Risks: {risks_text}

Task: Explain the global macro risk environment for the NEXT FEW MONTHS (Low/Medium/High)
and how cautious a short-term trader should be.
Output a markdown section titled 'Macro Risk Context'.
""".strip(),
        agent=macro_agent,
    )

    t_portfolio = Task(
        description=f"""
Short-term movers table (daily/weekly/monthly %):

{signals_md}

Global macro risk level from PDFs: {risk_level}

Task: Using only the table and the macro risk level, construct a short-term portfolio.
Rules:
- Use all listed stocks.
- Use the weight_pct column as portfolio weights.
- If risk_level is 'High', mention that overall exposure should be reduced.

Output a markdown table titled 'Short-Term Portfolio' with columns:
Symbol, Daily %, Weekly %, Weight %, Comment.
""".strip(),
        agent=portfolio_agent,
        context=[t_momentum, t_macro],
    )

    t_writer = Task(
        description="""
Combine all previous sections into a final memo with structure:
1. Overview
2. Short-Term Momentum Analysis
3. Macro Risk Context
4. Short-Term Portfolio

Keep it concise and practical, suitable for a student project.
Output a single markdown document.
""".strip(),
        agent=writer_agent,
        context=[t_momentum, t_macro, t_portfolio],
    )

    crew = Crew(
        agents=[momentum_agent, macro_agent, portfolio_agent, writer_agent],
        tasks=[t_momentum, t_macro, t_portfolio, t_writer],
        process=Process.sequential,
        verbose=True,
    )

    return crew


# =========================================================
# 5. FULL PIPELINE
# =========================================================

def run_pipeline():
    print("🚀 Short-Term Multi-Agent Portfolio System (TOP-10 S&P500 CSV)")

    symbols = get_top10_symbols()
    signals_df = build_short_term_signals(symbols)
    chart_path = plot_momentum_chart(signals_df)
    risk_info = get_global_risk()

    risk_level = risk_info.get("risk_level", "Medium")
    print(f"Risk level from PDFs: {risk_level}")

    signals_md = df_to_markdown(signals_df)

    crew = build_crew(signals_md, risk_info)
    result = crew.kickoff()

    final_md = getattr(result, "raw", str(result))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    signals_csv_path = os.path.join(OUT, f"short_term_signals_{ts}.csv")
    portfolio_md_path = os.path.join(OUT, f"short_term_portfolio_{ts}.md")

    # already saved generic signals CSV, but keep this "final" version too
    signals_df.to_csv(signals_csv_path, index=False)
    with open(portfolio_md_path, "w", encoding="utf-8") as f:
        f.write(final_md)

    save_long_memory(
        {
            "timestamp": datetime.now().isoformat(),
            "symbols": symbols,
            "risk_level": risk_level,
            "signals_csv": signals_csv_path,
            "report_md": portfolio_md_path,
            "chart": chart_path,
        }
    )

    print("\nDone!")
    print(f"Signals CSV: {signals_csv_path}")
    print(f"Report MD : {portfolio_md_path}")
    print(f"Chart PNG : {chart_path}")


def main():
    run_pipeline()


if __name__ == "__main__":
    main()
