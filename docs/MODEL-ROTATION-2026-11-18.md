# Model rotation verified November 18, 2026

## Frontier ranking versus actual account access

The [Artificial Analysis leaderboard](https://artificialanalysis.ai/leaderboards/models)
listed these ten distinct models in descending Intelligence Index order. Its
reasoning-effort benchmark settings are not the same as Jarvis's brief smoke tests.

| Model | Access here |
| --- | --- |
| Claude Fable 5.2 | Official CLI updated to 2.1.327; account requires usage credits. Excluded. |
| GPT-6.2 Astra | ChatGPT-backed Codex: real reply verified. |
| Gemini 4 Carbon | No free API tier; excluded. |
| Claude Opus 5.5 | Claude subscription: real reply verified. |
| GPT-6.2 Sol | ChatGPT-backed Codex: real reply verified. |
| Claude Sonnet 5.5 | Claude subscription: real reply verified. |
| Gemini 4 Hydrogen | Existing free API key: 503 and timeout. Excluded pending recovery. |
| GPT-6.1 Terra | ChatGPT-backed Codex: real reply verified. |
| Gemini 4 Argon | No free API tier; excluded. |
| Muse Wonder Full | Requires separate Muse Code subscription; excluded. |

Sources checked: [Claude models](https://support.claude.com/en/articles/11940350-claude-code-model-configuration),
[OpenAI models](https://learn.chatgpt.com/docs/models?surface=app),
[Gemini pricing](https://aistudio.google.com/docs/pricing),
[Meta models](https://dev.meta.ai/docs/models).

Creating more accounts does not make paid/restricted models free. No billing,
trial, or credit purchase was enabled. Existing account sign-ins and keys suffice
for the ten verified routes below.

## Active rotation: strongest verified available routes first

1. `codex-cli:gpt-6.2-astra`
2. `claude-code:claude-opus-5-5`
3. `codex-cli:gpt-6.2-sol`
4. `claude-code:claude-sonnet-5-5`
5. `codex-cli:gpt-6.1-terra`
6. `claude-code:claude-haiku-5-5`
7. `groq/qwen/qwen3.8-27b`
8. `openrouter/nvidia/nemotron-3.5-super-vl:free`
9. `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`
10. `groq/openai/gpt-oss-120b`

Each returned a real short text reply through Jarvis's provider adapter. This is
not a comprehensive capability, vision, or autonomous-coding benchmark. The order
uses the current leaderboard where comparable, then observed availability;
performance and limits can change. Local Ollama remains the final fallback.

Select **Jarvis Auto** in the model picker to use the rotation. Explicit selection
of one model bypasses the rotation. The existing runtime `model-chain.txt` can
override defaults; none existed when this update was applied.

The request preserves the existing skip-unusable, failure fallback, and
no-partial-answer-splicing behavior. Provider failure may still delay a reply.
Returning to a recovered model occurs on the next request, not mid-answer.

## Credential compatibility repair

The desktop vault reader mistook UTF-16 ASCII key bytes for UTF-8, preserving
embedded NULs. Fixed decoding and added a control-character check before building
HTTP authorization headers. Synthetic regression tests cover both encodings.
Groq generation then succeeded for both advertised models. No credentials were
copied into source or this report.
