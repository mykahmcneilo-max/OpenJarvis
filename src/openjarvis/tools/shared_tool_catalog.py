"""Read the shared tool inventory without running installers or integrations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openjarvis.core.paths import get_config_dir
from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


@ToolRegistry.register("shared_tool_catalog")
class SharedToolCatalog(BaseTool):
    """Bounded, local discovery shared by Jarvis, Codex and Claude."""

    tool_id = "shared_tool_catalog"

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_config_dir() / "shared-tools" / "catalog.json"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.tool_id,
            description=(
                "Find shared AI skills, tools and integrations by name or task. "
                "Returns installation state, local guide paths, and blockers. "
                "Inspiration and unavailable services are not executable tools. "
                "Read only the relevant guide; this tool never installs or runs code."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                },
            },
            category="skills",
        )

    def execute(self, **params: Any) -> ToolResult:
        try:
            query = params.get("query", "")
            if not isinstance(query, str) or len(query) > 500:
                raise ValueError("query must be text of at most 500 characters")
            limit = params.get("limit", 10)
            if isinstance(limit, bool) or not isinstance(limit, int):
                raise ValueError("limit must be an integer")
            limit = min(30, max(1, limit))
            data = json.loads(self._path.read_text(encoding="utf-8"))
            entries = data["tools"]
            words = query.casefold().split()
            matches = [
                item
                for item in entries
                if all(word in json.dumps(item).casefold() for word in words)
            ]
            body = {
                "matched": len(matches),
                "returned": min(limit, len(matches)),
                "tools": matches[:limit],
            }
        except (OSError, ValueError, KeyError, TypeError):
            return ToolResult(
                tool_name=self.tool_id,
                content="Shared catalog unavailable or invalid request.",
                success=False,
            )
        return ToolResult(
            tool_name=self.tool_id,
            content=json.dumps(body, ensure_ascii=False),
            success=True,
        )
