# Local tool requests

Run from the repository root with the offline dependencies installed.
Each input line is one JSON object; each response is one JSON line on stdout.
Blank lines are ignored. The process continues until stdin reaches EOF.
The scripts do not require Qwen credentials and do not invoke agents.

## Price tool

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_short_term_signals","arguments":{"symbols":["ALPHA","BETA"],"csv_path":"demo/prices.csv","as_of":"2025-02-11"}}}
```

`symbols` must be a nonempty list of ticker strings. `csv_path` selects a local
CSV; without it the legacy MARKET_CSV/default path is used. `as_of` is an
inclusive YYYY-MM-DD cutoff; omitting it uses the latest available observation.
Results include returns, illustrative weights and historical risk-window fields.

## Evidence tools

```json
{"jsonrpc":"2.0","id":"evidence","method":"tools/call","params":{"name":"rag_search_risk","arguments":{"query":"business risk","ticker":"ALPHA","k":3,"reports_dir":"demo/reports","as_of":"2025-02-11"}}}
```

`rag_search_risk` requires a string query and an explicit cutoff. `k` is an
integer from 1 to 10, not a Boolean. `ticker` defaults to `*`, which searches
shared sources only. A named ticker searches its own sources and shared sources.

`get_global_risk` takes the same reports_dir/as_of/ticker arguments without
query or k. It returns `risk_level: "Unassessed"`, an empty risks list and
retrieved evidence. It does not turn keyword counts into an investment risk rating.

## Response and error contract

Successful results use `result.content[0]` with `type: "text"`; its `text`
contains JSON for the tool result. IDs may be strings, integers or null and are
echoed on responses. Omitting id makes a notification: the tool is processed,
but no success/error reply is emitted. Invalid request objects receive a null ID.

| Error code | Meaning |
|---|---|
| -32700 | Invalid JSON; the next line is still processed |
| -32600 | Invalid request object, version, method type or ID type |
| -32601 | Method other than tools/call |
| -32602 | Unknown tool, malformed parameters, invalid input or file access failure |
| -32603 | Unexpected internal tool failure; implementation details are omitted |

Parameters and arguments must be JSON objects; positional arrays and request
batches are unsupported. File paths refer to the local process filesystem.
Only use these scripts as trusted local tools.

The shared dispatcher supports this small compatibility contract. There is no
MCP initialize/tools-list handshake, HTTP transport or network server.
