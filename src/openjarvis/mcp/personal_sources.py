"""Local stdio access to the same indexed sources Jarvis searches.

No credentials are copied and no network listener is opened. Clients control
when private search results enter their model context.
"""

from __future__ import annotations

import json
import sys
from typing import TextIO

from openjarvis.connectors.store import KnowledgeStore
from openjarvis.mcp.protocol import MCPRequest, MCPResponse
from openjarvis.mcp.server import MCPServer
from openjarvis.tools.knowledge_search import KnowledgeSearchTool
from openjarvis.tools.knowledge_sql import KnowledgeSQLTool
from openjarvis.tools.shared_tool_catalog import SharedToolCatalog


def serve(source: TextIO = sys.stdin, destination: TextIO = sys.stdout) -> None:
    """Serve bounded line-delimited MCP requests without stdout logging."""
    with KnowledgeStore() as store:
        server = MCPServer(
            tools=[
                KnowledgeSearchTool(store),
                KnowledgeSQLTool(store),
                SharedToolCatalog(),
            ]
        )
        for line in source:
            request_id = None
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    raise ValueError("Expected object")
                request_id = data.get("id")
                if request_id is None:
                    continue
                request = MCPRequest.from_json(line)
                response = (
                    MCPResponse(result={}, id=request_id)
                    if request.method == "ping"
                    else server.handle(request)
                )
            except (ValueError, KeyError, TypeError):
                response = MCPResponse.error_response(
                    request_id, -32600, "Invalid MCP request"
                )
            destination.write(response.to_json() + "\n")
            destination.flush()


if __name__ == "__main__":
    serve()
