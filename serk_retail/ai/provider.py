# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Language-model providers for SERK Retail AI (same convention as SERK Finance).

Configuration precedence: server environment (SERK_AI_PROVIDER, SERK_AI_MODEL, SERK_AI_API_KEY,
ANTHROPIC_API_KEY, OPENAI_API_KEY, SERK_AI_BASE_URL) then SERK AI Settings. Errors carry a
stable code that is safe to show; provider details stay in the server log.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import frappe
import requests

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4.1"}
TIMEOUT = 75


class AIError(Exception):
	def __init__(self, code: str, detail: str = ""):
		super().__init__(code)
		self.code = code
		self.detail = detail


@dataclass
class Config:
	provider: str  # anthropic | openai
	model: str
	api_key: str
	base_url: str
	max_tokens: int
	source: str  # environment | settings


def _settings():
	if not frappe.db.exists("DocType", "SERK AI Settings"):
		return None
	return frappe.get_cached_doc("SERK AI Settings")


def get_config() -> Config:
	s = _settings()
	if s is not None and not int(s.enabled or 0):
		raise AIError("ai_disabled", "AI is switched off in SERK AI Settings.")
	env_provider = (os.environ.get("SERK_AI_PROVIDER") or "").strip().lower()
	env_key = os.environ.get("SERK_AI_API_KEY") or ""
	if not env_key:
		env_key = os.environ.get("ANTHROPIC_API_KEY") if env_provider in ("", "anthropic") else os.environ.get("OPENAI_API_KEY")
		env_key = env_key or ""
	if env_key:
		provider = env_provider or "anthropic"
		source = "environment"
		model = os.environ.get("SERK_AI_MODEL") or DEFAULT_MODELS.get(provider, "")
		base_url = os.environ.get("SERK_AI_BASE_URL") or ""
		key = env_key
	elif s is not None and s.get_password("api_key", raise_exception=False):
		provider = {"Anthropic": "anthropic", "OpenAI": "openai", "OpenAI-compatible": "openai"}.get(s.provider, "anthropic")
		source = "settings"
		model = s.model or DEFAULT_MODELS[provider]
		base_url = s.base_url or ""
		key = s.get_password("api_key", raise_exception=False)
	else:
		raise AIError("ai_not_configured",
					  "Set SERK_AI_API_KEY on the server or an API key in SERK AI Settings.")
	if provider not in ("anthropic", "openai"):
		raise AIError("ai_bad_provider", f"Unknown provider {provider}.")
	if base_url and not base_url.startswith("https://"):
		raise AIError("ai_bad_base_url", "Base URL must use HTTPS.")
	max_tokens = int((s.max_tokens if s is not None else 0) or 1800)
	return Config(provider, model, key, base_url.rstrip("/"), max_tokens, source)


def complete(cfg: Config, system: str, messages: list[dict], max_tokens: int | None = None) -> dict:
	"""messages: [{"role": "user"|"assistant", "content": str}]. Returns {"text", "usage"}."""
	max_tokens = max_tokens or cfg.max_tokens
	try:
		if cfg.provider == "anthropic":
			url = (cfg.base_url or "https://api.anthropic.com") + "/v1/messages"
			r = requests.post(
				url,
				headers={"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
				json={"model": cfg.model, "max_tokens": max_tokens, "system": system, "messages": messages},
				timeout=TIMEOUT,
			)
		else:
			url = (cfg.base_url or "https://api.openai.com") + "/v1/chat/completions"
			r = requests.post(
				url,
				headers={"Authorization": f"Bearer {cfg.api_key}", "content-type": "application/json"},
				json={"model": cfg.model, "max_tokens": max_tokens,
					  "messages": [{"role": "system", "content": system}, *messages]},
				timeout=TIMEOUT,
			)
	except requests.Timeout:
		raise AIError("ai_timeout", "The AI provider did not answer in time.")
	except requests.RequestException as e:
		raise AIError("ai_unreachable", str(e)[:300])

	if r.status_code in (401, 403):
		raise AIError("ai_auth_failed", "The AI provider rejected the API key.")
	if r.status_code == 429:
		raise AIError("ai_rate_limited", "The AI provider is rate-limiting requests. Try again shortly.")
	if r.status_code >= 400:
		frappe.log_error(f"SERK AI {cfg.provider} HTTP {r.status_code}", r.text[:2000])
		raise AIError("ai_provider_error", f"HTTP {r.status_code}")
	data = r.json()
	if cfg.provider == "anthropic":
		text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
		usage = data.get("usage", {})
		usage = {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}
	else:
		text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
		u = data.get("usage", {})
		usage = {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens")}
	if not text.strip():
		raise AIError("ai_empty_answer", "The model returned no text.")
	return {"text": text.strip(), "usage": usage}
