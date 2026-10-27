"""Newline-delimited local JSON-RPC tools/call interface; not an MCP server."""
import json
import sys


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def dispatch(request, tools):
    if not isinstance(request, dict):
        return _error(None, -32600, "Request must be an object")
    request_id = request.get("id")
    if (request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str)
            or isinstance(request_id, bool)
            or not isinstance(request_id, (str, int, type(None)))):
        return _error(None, -32600, "Expected JSON-RPC 2.0, a method string and a string/integer/null ID")
    notification = "id" not in request
    if request["method"] != "tools/call":
        response = _error(request_id, -32601, "Only local tools/call is supported")
    else:
        try:
            params = request.get("params")
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            name = params.get("name")
            if not isinstance(name, str) or name not in tools:
                raise ValueError("Unknown tool")
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            result = tools[name](arguments)
            response = {"jsonrpc": "2.0", "id": request_id,
                        "result": {"content": [{"type": "text",
                                                "text": json.dumps(result, allow_nan=False)}]}}
        except (KeyError, ValueError, TypeError, OSError) as exc:
            response = _error(request_id, -32602, str(exc))
        except Exception:
            response = _error(request_id, -32603, "Internal tool error")
    return None if notification else response


def serve(handler, input_stream=None, output_stream=None):
    """Handle multiple newline-delimited requests until EOF, recovering from bad JSON."""
    input_stream = input_stream if input_stream is not None else sys.stdin
    output_stream = output_stream if output_stream is not None else sys.stdout
    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except (ValueError, TypeError):
            response = _error(None, -32700, "Invalid JSON")
        else:
            response = handler(request)
        if response is not None:
            output_stream.write(json.dumps(response) + "\n")
            output_stream.flush()
