"""Local JSON-RPC compatibility wrapper around dated lexical evidence retrieval.

This is not a complete Model Context Protocol server. No inferred Low/Medium/High
risk score is returned from keyword counts.
"""
from pathlib import Path
from evidence import load_evidence, retrieve
from local_rpc import dispatch, serve


def rag_search(query, k=5, reports_dir=None, as_of=None, ticker="*"):
    if not as_of:
        raise ValueError("as_of is required for historical document retrieval")
    folder = reports_dir or Path(__file__).parent / "data/reports"
    return retrieve(load_evidence(folder, as_of), ticker, query, k)


def get_global_risk(reports_dir=None, as_of=None, ticker="*"):
    evidence = rag_search("business risk debt uncertainty", 5, reports_dir, as_of, ticker)
    return {"risk_level": "Unassessed", "risks": [], "evidence": evidence}


def handle_call(request):
    return dispatch(request, {
        "get_global_risk": lambda args: get_global_risk(
            args.get("reports_dir"), args.get("as_of"), args.get("ticker", "*")),
        "rag_search_risk": lambda args: rag_search(
            args["query"], args.get("k", 5), args.get("reports_dir"),
            args.get("as_of"), args.get("ticker", "*")),
    })


if __name__ == "__main__":
    serve(handle_call)
