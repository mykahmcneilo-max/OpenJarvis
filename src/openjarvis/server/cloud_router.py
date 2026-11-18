"""Direct cloud API router — bypasses the engine system entirely.

Reads API keys from the process environment, with a legacy
~/.openjarvis/cloud-keys.env fallback for non-desktop/manual setups. Uses
httpx directly so no cloud SDK packages are required.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Sequence

import httpx

from openjarvis.core.paths import get_config_dir
from openjarvis.core.types import Message

# ---------------------------------------------------------------------------
# Key / provider detection
# ---------------------------------------------------------------------------

_CLOUD_ENV_FILE = get_config_dir() / "cloud-keys.env"

# Keys for the OpenAI-compatible providers (see OPENAI_COMPAT below).
_COMPAT_KEY_NAMES = (
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "MISTRAL_API_KEY",
    "MOONSHOT_API_KEY",
    "DEEPSEEK_API_KEY",
    "GITHUB_MODELS_TOKEN",
)

_OPENAI_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "chatgpt-")
_ANTHROPIC_PREFIXES = ("claude-",)
_GOOGLE_PREFIXES = ("gemini-",)
_MINIMAX_PREFIXES = ("MiniMax-",)
# Atlas Cloud IDs are already "vendor/model", so they must be recognised by
# their routing prefix before the generic '"/" means OpenRouter' fallback
# below — otherwise "atlascloud/openai/gpt-4.1-mini" is sent to OpenRouter.
_ATLASCLOUD_PREFIX = "atlascloud/"

# HuggingFace orgs that host local-only quantised models — never route to cloud.
_LOCAL_HF_ORGS = (
    "mlx-community/",
    "bartowski/",
    "unsloth/",
    "lmstudio-community/",
)


def _read_desktop_vault_key(vault: Any, name: str) -> str | None:
    """Read a key saved by the desktop app.

    The app's Rust keyring stores "<name>.<service>" with UTF-8 bytes, while
    Python keyring uses "<name>@<service>" with UTF-16, so check both.
    """
    try:
        cred = vault._read_credential(f"{name}.OpenJarvis Cloud Keys")
    except Exception:
        return None
    blob = (cred or {}).get("CredentialBlob")
    if not blob:
        return None
    if isinstance(blob, str):
        return blob
    try:
        # ASCII API keys encoded as UTF-16 also decode as UTF-8, with NULs.
        encoding = "utf-16-le" if b"\x00" in blob else "utf-8"
        text = blob.decode(encoding)
    except UnicodeDecodeError:
        text = blob.decode("utf-16-le", errors="ignore")
    return text.strip("\x00") or None


def _load_keys() -> dict[str, str]:
    """Read available cloud keys every call so live updates are picked up."""
    keys: dict[str, str] = {}
    # File first, then fall back to process environment
    if _CLOUD_ENV_FILE.exists():
        for raw in _CLOUD_ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                val = v.strip()
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    if len(val) >= 2:
                        val = val[1:-1]
                keys[k.strip()] = val
    # Process env can override (e.g. during testing)
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
        "MINIMAX_API_KEY",
        "ATLASCLOUD_API_KEY",
        "XAI_API_KEY",
        *_COMPAT_KEY_NAMES,
    ):
        val = os.environ.get(name)
        if val:
            keys[name] = val
    # The persistent service may start before Desktop; read its secure slots too.
    if os.name == "nt":
        try:
            from keyring.backends.Windows import WinVaultKeyring

            vault = WinVaultKeyring()
            for name in (
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "OPENROUTER_API_KEY",
                "MINIMAX_API_KEY",
                "ATLASCLOUD_API_KEY",
                "XAI_API_KEY",
                *_COMPAT_KEY_NAMES,
            ):
                if name not in keys:
                    value = vault.get_password(
                        "OpenJarvis Cloud Keys", name
                    ) or _read_desktop_vault_key(vault, name)
                    if value:
                        keys[name] = value
        except ImportError:
            pass
    return keys


# Subscription-backed official CLIs (billed to the user's existing plan, not
# a metered API key). Model ids: "claude-code[:<model>]" / "codex-cli[:<model>]".
_CLAUDE_CLI_PREFIX = "claude-code"
_CODEX_CLI_PREFIX = "codex-cli"
_XAI_PREFIXES = ("grok-",)
SUBSCRIPTION_PROVIDERS = {"claude_cli", "codex_cli"}
_CLI_TIMEOUT_SECONDS = 300

# OpenAI-compatible providers: id -> (model prefix, base URL, key name, label).
# Model ids are "<prefix><provider model id>", e.g. "groq/openai/gpt-oss-120b".
OPENAI_COMPAT: dict[str, tuple[str, str, str, str]] = {
    "groq": ("groq/", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "Groq"),
    "cerebras": (
        "cerebras/",
        "https://api.cerebras.ai/v1",
        "CEREBRAS_API_KEY",
        "Cerebras",
    ),
    "mistral": ("mistral/", "https://api.mistral.ai/v1", "MISTRAL_API_KEY", "Mistral"),
    "moonshot": (
        "kimi/",
        "https://api.moonshot.ai/v1",
        "MOONSHOT_API_KEY",
        "Kimi (Moonshot)",
    ),
    "deepseek": (
        "deepseek-api/",
        "https://api.deepseek.com",
        "DEEPSEEK_API_KEY",
        "DeepSeek API",
    ),
    "github": (
        "github/",
        "https://models.github.ai/inference",
        "GITHUB_MODELS_TOKEN",
        "GitHub Models",
    ),
}

# "jarvis-auto" walks this chain, best first, skipping models that aren't
# usable and moving on when one fails (quota/credits/rate limit/outage).
AUTO_MODEL = "jarvis-auto"
# Ranked usable routes checked 2026-11-18; local fallback follows this chain.
# Fable requires additional credits here; Gemini 4 routes were not healthy.
DEFAULT_MODEL_CHAIN = [
    "codex-cli:gpt-6.2-astra",
    "claude-code:claude-opus-5-5",
    "codex-cli:gpt-6.2-sol",
    "claude-code:claude-sonnet-5-5",
    "codex-cli:gpt-6.1-terra",
    "claude-code:claude-haiku-5-5",
    "groq/qwen/qwen3.8-27b",
    "openrouter/nvidia/nemotron-3.5-super-vl:free",
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    "groq/openai/gpt-oss-120b",
]


def _free_tier_providers() -> set[str]:
    """Providers the user confirmed have NO billing attached (free tier only).

    One provider id per line in ~/.openjarvis/free-tier-providers.txt. Only
    these (plus subscriptions and OpenRouter free routes) pass free-only mode.
    """
    path = get_config_dir() / "free-tier-providers.txt"
    try:
        return {
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
    except OSError:
        return set()


def model_chain() -> list[str]:
    """Ranked fallback chain (~/.openjarvis/model-chain.txt overrides)."""
    path = get_config_dir() / "model-chain.txt"
    try:
        custom = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if custom:
            return custom
    except OSError:
        pass
    return list(DEFAULT_MODEL_CHAIN)


def _cli_path(name: str) -> str | None:
    """Locate an official CLI (PATH, then the default per-user installs)."""
    import shutil
    from pathlib import Path

    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    candidates = {
        "claude": [home / ".local" / "bin" / "claude.exe", home / ".local/bin/claude"],
        "codex": [
            Path(os.environ.get("APPDATA", "")) / "npm" / "codex.cmd",
            home / ".npm-global" / "bin" / "codex",
        ],
    }.get(name, [])
    return next((str(p) for p in candidates if p.is_file()), None)


def _split_cli_model(model: str, prefix: str) -> str:
    """'claude-code:opus' -> 'opus'; 'claude-code' -> ''."""
    rest = model[len(prefix) :]
    return rest[1:] if rest.startswith((":", "/")) else ""


def get_provider(model: str) -> str | None:
    """Return the provider for a model name, or None if it's a local model."""
    if model == _CLAUDE_CLI_PREFIX or model.startswith(
        (_CLAUDE_CLI_PREFIX + ":", _CLAUDE_CLI_PREFIX + "/")
    ):
        return "claude_cli"
    if model == _CODEX_CLI_PREFIX or model.startswith(
        (_CODEX_CLI_PREFIX + ":", _CODEX_CLI_PREFIX + "/")
    ):
        return "codex_cli"
    if model == AUTO_MODEL:
        return "auto"
    for pid, (prefix, _base, _key, _label) in OPENAI_COMPAT.items():
        if model.startswith(prefix):
            return pid
    if any(model.startswith(p) for p in _XAI_PREFIXES):
        return "xai"
    # Bare GPT-OSS names and Ollama tags are local, despite the "gpt-" prefix.
    # Provider-qualified IDs (e.g. "openai/gpt-oss-20b") still route to cloud.
    if model == "gpt-oss" or model.startswith(("gpt-oss:", "gpt-oss-")):
        return None
    if any(model.startswith(p) for p in _OPENAI_PREFIXES):
        return "openai"
    if any(model.startswith(p) for p in _ANTHROPIC_PREFIXES):
        return "anthropic"
    if any(model.startswith(p) for p in _GOOGLE_PREFIXES):
        return "google"
    if any(model.startswith(p) for p in _MINIMAX_PREFIXES):
        return "minimax"
    if model.startswith(_ATLASCLOUD_PREFIX):
        return "atlascloud"
    if any(model.startswith(org) for org in _LOCAL_HF_ORGS):
        return None  # local model, never route to cloud
    if "/" in model:  # openrouter format: "meta-llama/llama-3-8b"
        return "openrouter"
    return None


def is_cloud_model(model: str) -> bool:
    """Return True if the model is served by a cloud provider."""
    return get_provider(model) is not None


def _openrouter_model_id(model: str) -> str:
    """Return the provider-facing ID for an OpenRouter model."""
    prefix = "openrouter/"
    candidate = model.removeprefix(prefix)
    # OpenRouter owns IDs such as "openrouter/auto" itself. Only remove the
    # LiteLLM routing prefix when the remainder is still a provider/model ID.
    if model.startswith(prefix) and "/" in candidate:
        return candidate
    return model


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------


def _to_openai_msgs(messages: Sequence[Message]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        role = m.role.value if hasattr(m.role, "value") else str(m.role)
        out.append({"role": role, "content": m.content or ""})
    return out


def _to_anthropic_msgs(
    messages: Sequence[Message],
) -> tuple[str, list[dict[str, Any]]]:
    """Return (system_text, chat_messages) in Anthropic format."""
    system_text = ""
    chat: list[dict[str, Any]] = []
    for m in messages:
        role = m.role.value if hasattr(m.role, "value") else str(m.role)
        if role == "system":
            system_text = m.content or ""
        else:
            # Anthropic only allows "user" and "assistant"
            ar = "user" if role != "assistant" else "assistant"
            chat.append({"role": ar, "content": m.content or ""})
    return system_text, chat


def _to_google_contents(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Convert to Google Gemini content format."""
    contents = []
    for m in messages:
        role = m.role.value if hasattr(m.role, "value") else str(m.role)
        if role == "system":
            # Gemini doesn't have a system role in the contents array;
            # prepend as a user message.
            contents.append({"role": "user", "parts": [{"text": m.content or ""}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": m.content or ""}]})
        else:
            contents.append({"role": "user", "parts": [{"text": m.content or ""}]})
    return contents


# ---------------------------------------------------------------------------
# Streaming generators
# ---------------------------------------------------------------------------


async def _stream_openai(
    model: str,
    messages: Sequence[Message],
    temperature: float,
    max_tokens: int,
    base_url: str = "https://api.openai.com/v1",
    api_key_name: str = "OPENAI_API_KEY",
) -> AsyncIterator[str]:
    keys = _load_keys()
    api_key = keys.get(api_key_name, "")
    if not api_key:
        raise ValueError(f"{api_key_name} not set — add it in the Cloud Models tab")
    if any(ord(char) < 33 or ord(char) > 126 for char in api_key):
        raise ValueError(f"{api_key_name} has invalid encoding; re-save it securely")

    payload = {
        "model": model,
        "messages": _to_openai_msgs(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream(
            "POST",
            f"{base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content") or ""
                    if delta:
                        yield delta
                except Exception:
                    pass


async def _stream_anthropic(
    model: str,
    messages: Sequence[Message],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    keys = _load_keys()
    api_key = keys.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set — add it in the Cloud Models tab")

    system_text, chat_msgs = _to_anthropic_msgs(messages)
    payload: dict[str, Any] = {
        "model": model,
        "messages": chat_msgs,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    if system_text:
        payload["system"] = system_text

    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                try:
                    event = json.loads(data)
                    if event.get("type") == "content_block_delta":
                        text = event.get("delta", {}).get("text", "")
                        if text:
                            yield text
                except Exception:
                    pass


async def _stream_google(
    model: str,
    messages: Sequence[Message],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    keys = _load_keys()
    api_key = keys.get("GEMINI_API_KEY") or keys.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set — add it in the Cloud Models tab")

    contents = _to_google_contents(messages)
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:streamGenerateContent?alt=sse&key={api_key}"
    )

    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                try:
                    chunk = json.loads(data)
                    parts = (
                        chunk.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [])
                    )
                    for part in parts:
                        text = part.get("text", "")
                        if text:
                            yield text
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Local (Ollama) direct streaming — bypasses engine routing entirely
# ---------------------------------------------------------------------------


def _ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


async def stream_local(
    model: str,
    messages: Sequence[Message],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> AsyncIterator[str]:
    """Stream tokens directly from Ollama, bypassing the engine system."""
    payload = {
        "model": model,
        "messages": _to_openai_msgs(messages),
        "stream": True,
        # Disable extended thinking (Qwen3.5 etc.) — when enabled all tokens
        # go into the 'thinking' field and 'content' stays empty.
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    host = _ollama_host()
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", f"{host}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break
                except Exception:
                    pass


async def list_local_models() -> list[str]:
    """Return Ollama model names directly from the Ollama API."""
    host = _ollama_host()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{host}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _flatten_for_cli(messages: Sequence[Message]) -> tuple[str, str]:
    """(system prompt, transcript prompt) for a one-shot CLI call."""
    system = "\n\n".join(
        m.content for m in messages if m.role.value == "system" and m.content
    )
    turns = [
        f"{'User' if m.role.value == 'user' else 'Assistant'}: {m.content}"
        for m in messages
        if m.role.value in ("user", "assistant") and m.content
    ]
    if len(turns) == 1:
        return system, turns[0].split(": ", 1)[1]
    return system, (
        "Conversation so far (continue it; reply only as the assistant):\n\n"
        + "\n\n".join(turns)
    )


def _cli_command(
    provider: str, model: str, system: str, prompt: str, workdir: Path
) -> tuple[list[str], str, Path | None]:
    """(argv, stdin prompt, output file) for a chat-only CLI call."""
    if provider == "claude_cli":
        exe = _cli_path("claude")
        if not exe:
            raise ValueError("Claude Code CLI not found; install it to use claude-code")
        args = [exe, "-p", "--output-format", "text", "--no-session-persistence"]
        args += ["--tools", ""]  # chat only: no file/shell/web tools
        sub_model = _split_cli_model(model, _CLAUDE_CLI_PREFIX)
        if sub_model:
            args += ["--model", sub_model]
        if system:
            args += ["--append-system-prompt", system]
        return args, prompt, None
    exe = _cli_path("codex")
    if not exe:
        raise ValueError("Codex CLI not found; install @openai/codex")
    out_file = workdir / "last.txt"
    args = [
        exe,
        "exec",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "-C",
        str(workdir),
        "-o",
        str(out_file),
    ]
    sub_model = _split_cli_model(model, _CODEX_CLI_PREFIX)
    if sub_model:
        args += ["-m", sub_model]
    args.append("-")  # prompt on stdin
    if system:
        prompt = f"{system}\n\n{prompt}"
    return args, prompt, out_file


def run_cli_sync(provider: str, model: str, system: str, prompt: str) -> str:
    """Blocking one-shot CLI call (for engines called from worker threads)."""
    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="oj-cli-") as workdir:
        args, stdin, out_file = _cli_command(
            provider, model, system, prompt, Path(workdir)
        )
        try:
            proc = subprocess.run(
                args,
                input=stdin.encode("utf-8"),
                capture_output=True,
                cwd=workdir,
                timeout=_CLI_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                f"{provider} timed out after {_CLI_TIMEOUT_SECONDS}s"
            ) from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).decode("utf-8", "replace")
            raise ValueError(f"{provider} failed: {detail.strip()[-300:]}")
        if out_file is not None and out_file.is_file():
            return out_file.read_text(encoding="utf-8").strip()
        return proc.stdout.decode("utf-8", "replace").strip()


async def _stream_cli(
    provider: str, model: str, messages: Sequence[Message]
) -> AsyncIterator[str]:
    """Run Claude Code / Codex CLI in a chat-only, no-tools mode."""
    import asyncio
    import tempfile
    from pathlib import Path

    system, prompt = _flatten_for_cli(messages)
    with tempfile.TemporaryDirectory(prefix="oj-cli-") as workdir:
        args, prompt, out_file = _cli_command(
            provider, model, system, prompt, Path(workdir)
        )
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        try:
            out, err = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8")), _CLI_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise ValueError(f"{provider} timed out after {_CLI_TIMEOUT_SECONDS}s")
        if proc.returncode != 0:
            detail = (err or out).decode("utf-8", "replace").strip()[-300:]
            raise ValueError(f"{provider} failed: {detail or proc.returncode}")
        if out_file is not None and out_file.is_file():
            text = out_file.read_text(encoding="utf-8")
        else:
            text = out.decode("utf-8", "replace")
    if text.strip():
        yield text.strip()


def _usable_models() -> dict[str, bool]:
    """provider id -> usable now (authorized and not blocked)."""
    return {row["id"]: row["usable"] for row in provider_status()}


async def _stream_auto(
    messages: Sequence[Message], temperature: float, max_tokens: int
) -> AsyncIterator[str]:
    """Try the ranked chain; on failure before any output, use the next one.

    Falls back to the local default model last, so a reply always comes.
    The first chunk names the model that answered (``[via <model>]``) only
    in logs; the UI gets it from response metadata.
    """
    import logging

    log = logging.getLogger(__name__)
    usable = _usable_models()
    tried: list[str] = []
    for candidate in model_chain():
        provider = get_provider(candidate)
        if provider is None or not usable.get(provider, False):
            continue
        tried.append(candidate)
        produced = False
        try:
            async for token in stream_cloud(
                candidate, messages, temperature, max_tokens
            ):
                produced = True
                yield token
            if produced:
                LAST_AUTO_MODEL["model"] = candidate
                return
        except Exception as exc:
            if produced:  # partial answer already sent; don't splice another
                return
            log.warning("jarvis-auto: %s failed (%s); trying next", candidate, exc)
    local = os.environ.get("OPENJARVIS_LOCAL_FALLBACK_MODEL", "qwen3.5:9b")
    log.warning("jarvis-auto: falling back to local %s after %s", local, tried)
    LAST_AUTO_MODEL["model"] = local
    async for token in stream_local(local, messages, temperature, max_tokens):
        yield token


# Which chain entry answered the most recent jarvis-auto request.
LAST_AUTO_MODEL: dict[str, str] = {"model": ""}


def provider_status() -> list[dict[str, Any]]:
    """Which providers are usable right now, and how they're paid for.

    Never returns key values. ``authorized`` reflects what is actually
    configured on this machine; nothing here enables billing.
    """
    keys = _load_keys()
    free_only = (get_config_dir() / "free-cloud-only").exists()
    from pathlib import Path

    claude_signed_in = (Path.home() / ".claude" / ".credentials.json").is_file()
    codex_signed_in = (Path.home() / ".codex" / "auth.json").is_file()
    rows: list[dict[str, Any]] = [
        {
            "id": "claude_cli",
            "label": "Claude (Claude Code subscription)",
            "billing": "subscription",
            "installed": bool(_cli_path("claude")),
            "authorized": bool(_cli_path("claude")) and claude_signed_in,
            "models": [
                "claude-code:claude-opus-5-5",
                "claude-code:claude-sonnet-5-5",
                "claude-code:claude-haiku-5-5",
            ],
        },
        {
            "id": "codex_cli",
            "label": "Codex (ChatGPT subscription)",
            "billing": "subscription",
            "installed": bool(_cli_path("codex")),
            "authorized": bool(_cli_path("codex")) and codex_signed_in,
            "models": [
                "codex-cli:gpt-6.2-astra",
                "codex-cli:gpt-6.2-sol",
                "codex-cli:gpt-6.1-terra",
            ],
        },
    ]
    metered = [
        ("anthropic", "Claude API", "ANTHROPIC_API_KEY", ["claude-sonnet-4-5"]),
        ("openai", "OpenAI API", "OPENAI_API_KEY", ["gpt-5", "gpt-4.1"]),
        ("xai", "xAI Grok API", "XAI_API_KEY", ["grok-4", "grok-3-mini"]),
        (
            "google",
            "Google Gemini API",
            "GEMINI_API_KEY",
            ["gemini-3.8-flash", "gemini-3.5-flash-lite"],
        ),
        ("openrouter", "OpenRouter", "OPENROUTER_API_KEY", ["openrouter/free"]),
    ]
    compat_models = {
        "groq": ["groq/openai/gpt-oss-120b", "groq/qwen/qwen3.8-27b"],
        "cerebras": [
            "cerebras/llama-3.3-70b",
            "cerebras/qwen-3-235b-a22b-instruct-2507",
        ],
        "mistral": ["mistral/mistral-large-latest", "mistral/codestral-latest"],
        "moonshot": ["kimi/kimi-k2-0905-preview"],
        "deepseek": ["deepseek-api/deepseek-chat", "deepseek-api/deepseek-reasoner"],
        "github": ["github/openai/gpt-4.1", "github/deepseek/DeepSeek-R1"],
    }
    for pid, (_prefix, _base, key, label) in OPENAI_COMPAT.items():
        metered.append((pid, label, key, compat_models.get(pid, [])))
    free_tier = _free_tier_providers()
    for pid, label, key, models in metered:
        has_key = bool(
            keys.get(key) or (pid == "google" and keys.get("GOOGLE_API_KEY"))
        )
        rows.append(
            {
                "id": pid,
                "label": label,
                "billing": "metered_api",
                "key_name": key,
                "authorized": has_key,
                "models": models,
            }
        )
    for row in rows:
        row["free_tier_confirmed"] = row["id"] in free_tier
        blocked = (
            free_only
            and row["billing"] == "metered_api"
            and row["id"] != "openrouter"
            and not row["free_tier_confirmed"]
        )
        row["blocked_by_free_only"] = blocked
        if not row["authorized"]:
            if row["billing"] == "subscription":
                row["detail"] = (
                    "Not installed" if not row.get("installed") else "Not signed in"
                )
            else:
                row["detail"] = f"Needs {row['key_name']}"
        elif blocked:
            row["detail"] = (
                "Key found, but free-only mode blocks it until you confirm the "
                "account has no billing attached"
            )
        elif row["free_tier_confirmed"]:
            row["detail"] = "Ready (free tier, no billing attached)"
        else:
            row["detail"] = "Ready"
        row["usable"] = row["authorized"] and not blocked
    return rows


async def stream_cloud(
    model: str,
    messages: Sequence[Message],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> AsyncIterator[str]:
    """Stream tokens from a cloud provider for the given model."""
    provider = get_provider(model)
    if (get_config_dir() / "free-cloud-only").exists():
        # Subscription CLIs bill the user's existing plan, not a metered key,
        # so they stay allowed; every metered API route stays blocked.
        free_route = (
            provider in SUBSCRIPTION_PROVIDERS
            or provider == "auto"  # each candidate is checked on its own
            or provider in _free_tier_providers()
            or (
                provider == "openrouter"
                and (
                    _openrouter_model_id(model).endswith(":free")
                    or _openrouter_model_id(model) == "openrouter/free"
                )
            )
        )
        if not free_route:
            raise ValueError(
                "Free-only mode: this API route is not verified free. "
                "Use local Ollama, your Claude/Codex subscription, or an "
                "OpenRouter free model."
            )

    if provider == "auto":
        async for token in _stream_auto(messages, temperature, max_tokens):
            yield token

    elif provider in SUBSCRIPTION_PROVIDERS:
        async for token in _stream_cli(provider, model, messages):
            yield token

    elif provider in OPENAI_COMPAT:
        prefix, base_url, key_name, _label = OPENAI_COMPAT[provider]
        async for token in _stream_openai(
            model[len(prefix) :],
            messages,
            temperature,
            max_tokens,
            base_url=base_url,
            api_key_name=key_name,
        ):
            yield token

    elif provider == "xai":
        async for token in _stream_openai(
            model,
            messages,
            temperature,
            max_tokens,
            base_url="https://api.x.ai/v1",
            api_key_name="XAI_API_KEY",
        ):
            yield token

    elif provider == "openai":
        async for token in _stream_openai(model, messages, temperature, max_tokens):
            yield token

    elif provider == "anthropic":
        async for token in _stream_anthropic(model, messages, temperature, max_tokens):
            yield token

    elif provider == "google":
        async for token in _stream_google(model, messages, temperature, max_tokens):
            yield token

    elif provider == "openrouter":
        keys = _load_keys()
        api_key = keys.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set — add it in the Cloud Models tab"
            )
        async for token in _stream_openai(
            _openrouter_model_id(model),
            messages,
            temperature,
            max_tokens,
            base_url="https://openrouter.ai/api/v1",
            api_key_name="OPENROUTER_API_KEY",
        ):
            yield token

    elif provider == "atlascloud":
        keys = _load_keys()
        api_key = keys.get("ATLASCLOUD_API_KEY", "")
        if not api_key:
            raise ValueError(
                "ATLASCLOUD_API_KEY not set — add it in the Cloud Models tab"
            )
        async for token in _stream_openai(
            model.removeprefix(_ATLASCLOUD_PREFIX),
            messages,
            temperature,
            max_tokens,
            base_url="https://api.atlascloud.ai/v1",
            api_key_name="ATLASCLOUD_API_KEY",
        ):
            yield token

    elif provider == "minimax":
        keys = _load_keys()
        api_key = keys.get("MINIMAX_API_KEY", "")
        if not api_key:
            raise ValueError("MINIMAX_API_KEY not set — add it in the Cloud Models tab")
        async for token in _stream_openai(
            model,
            messages,
            temperature,
            max_tokens,
            base_url="https://api.minimax.io/v1",
            api_key_name="MINIMAX_API_KEY",
        ):
            yield token

    else:
        raise ValueError(f"Unknown cloud provider for model: {model!r}")
