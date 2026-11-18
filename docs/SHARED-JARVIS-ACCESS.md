# Shared Jarvis access and model verification

Updated 2026-11-18.

The local MCP server `jarvis-personal` is registered in Codex, Claude Code user configuration, and Claude Desktop configuration. Restart the relevant app or start a new session to load it. Launcher: `C:/Users/Uoza/OpenJarvis/.venv/Scripts/python.exe -m openjarvis.mcp.personal_sources`.

It exposes `knowledge_search` and read-only `knowledge_sql` over the same knowledge.db used by Jarvis. All indexed sources are searchable; tokens and passwords are not copied. Source records returned to a cloud assistant become part of that assistant's context. This does not automatically grant live school, browser, messaging-send, or account administration access. Existing local coding tools remain available to local coding sessions.

For assignment requests, query available indexed sources and report source and freshness. There is currently no D2L connector/source, so do not claim a complete assignment list. School authentication and an authorized integration/import are still needed. Never submit coursework or mark assignments done merely because they were retrieved.

Verified through Jarvis provider adapters: Claude subscription Opus and ChatGPT-backed Codex each returned OK. Existing sign-ins were reused; no new account or billing was needed. Added OpenRouter free choices Nemotron Ultra 550B, Nemotron Super VL, and Gemma 4 31B after checking the live catalog reports zero prompt/completion price. Ultra returned OK through Jarvis; the other two are catalog-verified, not generation-tested. Free availability and limits may change. Grok has no configured authorization and must remain unavailable until legitimate access exists.

An hourly heartbeat named Hourly Jarvis health checks was created in the current Codex chat. It checks readiness and bounded regressions without paid calls or outbound messages. It depends on the scheduler and local PC/executor access; it does not guarantee every feature or phone delivery.
