"""Personal-source bridge exposes search, never sending or credential tools."""

import io
import json

from openjarvis.mcp.personal_sources import serve


def test_stdio_discovery_and_readonly_call(tmp_path, monkeypatch):
    from openjarvis.connectors.store import KnowledgeStore

    monkeypatch.setattr(
        "openjarvis.mcp.personal_sources.KnowledgeStore",
        lambda: KnowledgeStore(tmp_path / "knowledge.db"),
    )
    requests = [
        {"id": 1, "method": "initialize"},
        {"method": "notifications/initialized"},
        {"id": 2, "method": "tools/list"},
        {
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "knowledge_sql",
                "arguments": {"query": "DELETE FROM knowledge_chunks"},
            },
        },
        {"id": 4, "method": "ping"},
    ]
    output = io.StringIO()
    serve(io.StringIO("\n".join(map(json.dumps, requests))), output)
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(responses) == 4
    assert {t["name"] for t in responses[1]["result"]["tools"]} == {
        "knowledge_search",
        "knowledge_sql",
        "shared_tool_catalog",
    }
    assert responses[2]["result"]["isError"] is True
    assert responses[3]["result"] == {}
