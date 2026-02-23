from __future__ import annotations


import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

# Allow running this script directly from repository root:
# `python tools/test_llm_cli.py ...`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.llm import LLMConfig, LLMProvider


Message = Dict[str, str]


_ENV_PLACEHOLDER_RE = re.compile(r"^<([A-Z0-9_]+)>$")


def _resolve_env_placeholder(value: str) -> str:
    """
    Support config values like "<BAILIAN_API_KEY>".
    If not in that format, return original string.
    """
    s = value.strip()
    m = _ENV_PLACEHOLDER_RE.fullmatch(s)
    if not m:
        return value
    env_name = m.group(1)
    env_val = os.getenv(env_name)
    if not env_val:
        raise RuntimeError(f"Environment variable '{env_name}' is not set")
    return env_val


def _fixup_provider_env_placeholders(cfg: LLMConfig) -> None:
    """
    If user hasn't implemented placeholder parsing in LLMConfig yet,
    this makes the CLI usable immediately by resolving ProviderSettings fields.
    """
    for name, ps in cfg.providers.items():
        if isinstance(ps.api_key, str):
            ps.api_key = _resolve_env_placeholder(ps.api_key)
        if isinstance(ps.api_base, str):
            ps.api_base = _resolve_env_placeholder(ps.api_base)


def _pick_default_provider_model(cfg: LLMConfig) -> tuple[str, str]:
    provider = cfg.default_provider
    if not provider:
        # fallback: first provider in dict
        if not cfg.providers:
            raise RuntimeError("No providers configured in config/llm.yaml")
        provider = next(iter(cfg.providers.keys()))

    preferred = cfg.default_models.get(provider) or []
    if preferred:
        model = preferred[0]
    else:
        model_map = cfg.models.get(provider, {})
        if not model_map:
            raise RuntimeError(f"No models configured for provider '{provider}'")
        model = next(iter(model_map.keys()))
    return provider, model


def _print_help() -> None:
    print(
        "\nCommands:\n"
        "  /help                  show this help\n"
        "  /provider <name>        switch provider (e.g. bailian / ollama)\n"
        "  /model <name>           switch model (e.g. qwen-max)\n"
        "  /system <text>          set/replace system prompt\n"
        "  /clear                  clear conversation (keeps system prompt)\n"
        "  /params key=value ...   set default params (temperature=0.2 max_tokens=1024)\n"
        "  /show                   show current provider/model/params\n"
        "  /exit                   quit\n"
    )


def _parse_kv_tokens(tokens: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for t in tokens:
        if "=" not in t:
            raise ValueError(f"Invalid param '{t}', expected key=value")
        k, v = t.split("=", 1)
        k = k.strip()
        v = v.strip()

        # best-effort type casting
        if v.lower() in ("true", "false"):
            out[k] = (v.lower() == "true")
            continue
        try:
            if "." in v:
                out[k] = float(v)
            else:
                out[k] = int(v)
            continue
        except ValueError:
            pass
        out[k] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Interactive LLM test CLI (uses config/llm.yaml)")
    ap.add_argument("--config", default="config/llm.yaml", help="Path to llm.yaml")
    ap.add_argument("--provider", default=None, help="Provider name (bailian/ollama/...)")
    ap.add_argument("--model", default=None, help="Model name")
    ap.add_argument("--system", default="", help="Optional system prompt")
    ap.add_argument("--temperature", type=float, default=None, help="Default temperature")
    ap.add_argument("--max_tokens", type=int, default=None, help="Default max_tokens")
    args = ap.parse_args()

    cfg = LLMConfig.load(args.config)
    _fixup_provider_env_placeholders(cfg)

    provider, model = _pick_default_provider_model(cfg)
    if args.provider:
        provider = args.provider
    if args.model:
        model = args.model

    # default params
    default_params: Dict[str, Any] = {}
    if args.temperature is not None:
        default_params["temperature"] = args.temperature
    if args.max_tokens is not None:
        default_params["max_tokens"] = args.max_tokens

    gateway = LLMProvider(provider, model, config=cfg, default_params=default_params)

    system_prompt = args.system.strip()
    messages: List[Message] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    print("══════════════════════════════════════════════════════════════")
    print("🧪 LLM Test CLI")
    print(f"Config:   {args.config}")
    print(f"Provider: {provider}")
    print(f"Model:    {model}")
    print(f"Params:   {default_params or '(none)'}")
    if system_prompt:
        print(f"System:   {system_prompt}")
    print("Type /help for commands. Type /exit to quit.")
    print("══════════════════════════════════════════════════════════════\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return 0

        if not line:
            continue

        # commands
        if line.startswith("/"):
            parts = line.split()
            cmd = parts[0].lower()

            if cmd in ("/help", "/h"):
                _print_help()
                continue

            if cmd == "/exit":
                return 0

            if cmd == "/show":
                print(f"Provider: {provider}")
                print(f"Model:    {model}")
                print(f"Params:   {default_params or '(none)'}")
                if system_prompt:
                    print(f"System:   {system_prompt}")
                continue

            if cmd == "/provider":
                if len(parts) < 2:
                    print("usage: /provider <name>")
                    continue
                new_provider = parts[1]
                if new_provider not in cfg.providers:
                    print(f"unknown provider: {new_provider} (configured: {list(cfg.providers.keys())})")
                    continue
                provider = new_provider
                # pick a default model for this provider if current doesn't exist
                if model not in cfg.models.get(provider, {}):
                    provider, model = _pick_default_provider_model(cfg)
                gateway = LLMProvider(provider, model, config=cfg, default_params=default_params)
                print(f"switched provider -> {provider}, model -> {model}")
                continue

            if cmd == "/model":
                if len(parts) < 2:
                    print("usage: /model <name>")
                    continue
                new_model = parts[1]
                if new_model not in cfg.models.get(provider, {}):
                    print(f"unknown model '{new_model}' for provider '{provider}'")
                    print(f"available: {list(cfg.models.get(provider, {}).keys())}")
                    continue
                model = new_model
                gateway = LLMProvider(provider, model, config=cfg, default_params=default_params)
                print(f"switched model -> {model}")
                continue

            if cmd == "/system":
                system_prompt = " ".join(parts[1:]).strip()
                # rebuild messages but keep history? MVP: reset with new system prompt
                user_assistant = [m for m in messages if m.get("role") in ("user", "assistant")]
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.extend(user_assistant)
                print("system prompt updated")
                continue

            if cmd == "/clear":
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                print("conversation cleared")
                continue

            if cmd == "/params":
                try:
                    kv = _parse_kv_tokens(parts[1:])
                except Exception as e:
                    print(f"params error: {e}")
                    continue
                default_params.update(kv)
                gateway = LLMProvider(provider, model, config=cfg, default_params=default_params)
                print(f"default params updated -> {default_params}")
                continue

            print(f"unknown command: {cmd} (try /help)")
            continue

        # user message -> call llm
        messages.append({"role": "user", "content": line})
        try:
            reply = gateway.call(messages)
        except Exception as e:
            print(f"[error] {e}")
            # keep the user msg, but don't append assistant msg
            continue

        print(reply)
        messages.append({"role": "assistant", "content": reply})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
