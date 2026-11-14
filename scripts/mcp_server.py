"""Minimal MCP-compatible stdio tool server (stdlib only, one file).

Exposes exactly two tools over JSON-RPC on stdio:
- search_policies(query, k=3): ranked policy clauses
- get_checklist(employee_id, role, location): first-week checklist

Usage: python scripts/mcp_server.py < requests.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graph import Copilot  # noqa: E402

TOOLS = [
    {
        "name": "search_policies",
        "description": "Search the synthetic HR policy corpus for clauses matching a question.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_checklist",
        "description": "Build a personalised first-week onboarding checklist for a new joiner.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "role": {"type": "string"},
                "location": {"type": "string"},
            },
            "required": ["employee_id", "role", "location"],
        },
    },
]


def main() -> None:
    copilot = Copilot(audit_path=None)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params", {}) or {}

        def reply(result=None, error=None):
            msg = {"jsonrpc": "2.0", "id": req_id}
            if error is not None:
                msg["error"] = {"code": -32602, "message": error}
            else:
                msg["result"] = result
            sys.stdout.write(json.dumps(msg) + "\n")
            sys.stdout.flush()

        if method == "initialize":
            reply({"protocolVersion": "2024-11-05",
                   "capabilities": {"tools": {}},
                   "serverInfo": {"name": "hr-policy-copilot", "version": "0.1.0"}})
        elif method == "tools/list":
            reply({"tools": TOOLS})
        elif method == "tools/call":
            try:
                name = params.get("name")
                args = params.get("arguments", {}) or {}
                if name == "search_policies":
                    if not isinstance(args.get("query"), str) or not args["query"]:
                        raise ValueError("search_policies requires a non-empty string 'query'")
                    try:
                        k = int(args.get("k", 3))
                    except (TypeError, ValueError):
                        raise ValueError("k must be an integer") from None
                    k = max(1, min(10, k))
                    scored = copilot.retriever.retrieve(args["query"], k=k)
                    reply({"content": [{"type": "text", "text": json.dumps([
                        {"doc_id": s.clause.doc_id, "clause_id": s.clause.clause_id,
                         "title": s.clause.title, "quote": s.clause.text,
                         "score": round(s.score, 3)} for s in scored])}]})
                elif name == "get_checklist":
                    for field in ("employee_id", "role", "location"):
                        if not isinstance(args.get(field), str) or not args[field]:
                            raise ValueError(f"get_checklist requires a non-empty string '{field}'")
                    result = copilot.checklist(args["employee_id"], args["role"], args["location"])
                    reply({"content": [{"type": "text", "text": json.dumps(result)}]})
                else:
                    reply(error=f"unknown tool: {name}")
            except Exception as exc:  # noqa: BLE001 - bad args must be a JSON-RPC error, not a crash
                reply(error=f"tools/call failed: {exc}")
        else:
            reply(error=f"unknown method: {method}")


if __name__ == "__main__":
    main()
