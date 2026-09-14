"""Env-driven configuration for the AI layer."""
import os

PROVIDER_URL = os.environ.get("CLAUDE_PROVIDER_URL", "http://127.0.0.1:3111").rstrip("/")
# Shared with the provider (PROVIDER_SHARED_SECRET there). It travels as
# X-Provider-Token and is what lets a chat name a client's Amazon Ads account;
# empty keeps the network-only perimeter of local runs.
PROVIDER_SECRET = os.environ.get("CLAUDE_PROVIDER_SECRET", "").strip()
AI_ENABLED = os.environ.get("AI_ENABLED", "1").strip().lower() not in ("0", "false", "no")
LOG_DIR = os.environ.get("AI_LOG_DIR", os.path.join("data", "ai", "log"))
