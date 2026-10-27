"""Local JSON-RPC compatibility wrapper around dated lexical evidence retrieval.

This is not a complete Model Context Protocol server. No inferred Low/Medium/High
risk score is returned from keyword counts.
"""
import json
import sys
from pathlib import Path
from evidence import load_evidence, retrieve


def rag_search(query, k=5, reports_dir=None, as_of=None, ticker="*"):
    if not as_of:
        raise ValueError("as_of is required for historical document retrieval")
    folder = reports_dir or Path(__file__).parent / "data/reports"
    return retrieve(load_evidence(folder, as_of), ticker, query, k)


def get_global_risk(reports_dir=None, as_of=None, ticker="*"):
    evidence = rag_search("business risk debt uncertainty", 5, reports_dir, as_of, ticker)
    return {"risk_level": "Unassessed", "risks": [], "evidence": evidence}


def handle_call(request):
    try:
        if request.get("method") != "tools/call":
            raise ValueError("Only local tools/call is supported")
        params = request["params"]
        args = params.get("arguments", {})
        if params["name"] == "get_global_risk":
            result = get_global_risk(args.get("reports_dir"), args.get("as_of"), args.get("ticker", "*"))
        elif params["name"] == "rag_search_risk":
            result = rag_search(args["query"], args.get("k", 5), args.get("reports_dir"),
                                args.get("as_of"), args.get("ticker", "*"))
        else:
            raise ValueError("Unknown tool")
        return {"jsonrpc": "2.0", "id": request.get("id"),
                "result": {"content": [{"type": "text", "text": json.dumps(result)}]}}
    except (KeyError, ValueError, TypeError, OSError) as exc:
        return {"jsonrpc": "2.0", "id": request.get("id"),
                "error": {"code": -32602, "message": str(exc)}}


if __name__ == "__main__":
    try:
        request = json.loads(sys.stdin.readline())
        if not isinstance(request, dict):
            raise ValueError("Request must be an object")
        print(json.dumps(handle_call(request)))
    except (ValueError, TypeError):
        print(json.dumps({"jsonrpc": "2.0", "id": None,
                          "error": {"code": -32700, "message": "Invalid JSON"}}))
