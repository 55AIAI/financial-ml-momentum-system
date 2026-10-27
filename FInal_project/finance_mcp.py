"""Compatibility entry point; the maintained implementation is at repository root."""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if __name__ == "__main__":
    runpy.run_path(str(ROOT / "finance_mcp.py"), run_name="__main__")
