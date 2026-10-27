import sys
import os
import json
import traceback
from typing import Dict, Any, List

from dotenv import load_dotenv
from pypdf import PdfReader

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
PDF_DIR = os.path.join(DATA, "pdf")


# ---------- PDF loading ----------

def load_pdf_texts() -> List[str]:
    texts: List[str] = []
    for fn in ["gfsr.pdf", "oecd.pdf"]:
        path = os.path.join(PDF_DIR, fn)
        if not os.path.exists(path):
            # log only to stderr
            print(f"[pdf_mcp] WARNING: PDF missing: {path}", file=sys.stderr)
            continue
        try:
            reader = PdfReader(path)
            pages = [(p.extract_text() or "") for p in reader.pages]
            texts.append("\n".join(pages))
        except Exception as e:
            print(f"[pdf_mcp] ERROR reading {path}: {e}", file=sys.stderr)
    return texts


# ---------- simple RAG index (no vectors) ----------

def build_docs() -> List[Document]:
    texts = load_pdf_texts()
    if not texts:
        return []

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    docs: List[Document] = []
    for t in texts:
        for chunk in splitter.split_text(t):
            docs.append(Document(page_content=chunk))
    return docs


DOCS: List[Document] = build_docs()


def rag_search(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """Very simple lexical retrieval over PDF chunks."""
    if not DOCS:
        raise FileNotFoundError("Financial risk reports are missing. Add source PDFs before risk analysis.")

    words = [w.lower() for w in query.split() if len(w) > 3]
    scored: List[tuple] = []

    for i, d in enumerate(DOCS):
        text = d.page_content.lower()
        score = sum(text.count(w) for w in words)
        if score > 0:
            scored.append((score, d.page_content))

    if not scored:
        # fallback: first k docs
        return [
            {"id": str(i), "content": d.page_content[:1000]}
            for i, d in enumerate(DOCS[:k])
        ]

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:k]
    return [{"id": str(i), "content": t[:1000]} for i, (s, t) in enumerate(top)]


# ---------- risk estimation ----------

RISK_WORDS = {
    "volatility": 2,
    "uncertainty": 1,
    "instability": 2,
    "crisis": 3,
    "stress": 2,
    "default": 3,
    "debt": 1,
    "risk": 1,
    "vulnerab": 2,  # vulnerable / vulnerability
}


def analyze_risk_from_text(context: str) -> Dict[str, Any]:
    text = context.lower()
    score = 0
    for w, w_score in RISK_WORDS.items():
        score += text.count(w) * w_score

    # Very rough heuristic
    if score < 30:
        level = "Low"
    elif score < 80:
        level = "Medium"
    else:
        level = "High"

    bullets = [
        "Macro-financial vulnerabilities are discussed across the reports.",
        "Authorities monitor debt, volatility and financial stability indicators.",
    ]
    return {"risk_level": level, "risks": bullets, "raw_score": score}


def get_global_risk() -> Dict[str, Any]:
    chunks = rag_search(
        "global macro risk, financial stability, volatility, debt, uncertainty", k=8
    )
    ctx = "\n\n".join(c.get("content", "") for c in chunks)
    if not any(c.get("content") for c in chunks):
        raise ValueError("No risk evidence was retrieved; refusing to assign a risk level.")
    info = analyze_risk_from_text(ctx)
    # Drop raw_score from external API response
    return {"risk_level": info["risk_level"], "risks": info["risks"]}


# ---------- MCP handler ----------

def handle_call(req: Dict[str, Any]) -> Dict[str, Any]:
    name = req.get("params", {}).get("name")
    args = req.get("params", {}).get("arguments", {})

    try:
        if name == "get_global_risk":
            res = get_global_risk()
        elif name == "rag_search_risk":
            q = args.get("query", "")
            k = int(args.get("k", 5))
            res = rag_search(q, k)
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

    except Exception:
        return {
            "jsonrpc": "2.0",
            "id": req.get("id"),
            "error": {
                "code": -32000,
                "message": "Internal error in pdf_mcp",
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
                        "message": "Fatal server crash in pdf_mcp",
                        "details": err,
                    },
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
