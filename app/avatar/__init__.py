"""
Avatar provider integration.

Today the Python app does NOT call Tavus directly. Tavus calls our
/v1/chat/completions endpoint (configured via scripts/Update-NathanPersonaLLM.ps1).
The persona is created and configured out-of-band in the Tavus dashboard.

This package exists to:
  1. Be the single place that reads TAVUS_* env vars (no scattered os.getenv calls)
  2. Surface provider status in /readiness so we can verify configuration
  3. Hold a future Python TavusClient when we need to create/end conversations
     programmatically (e.g., "join this Teams meeting via Nathan" endpoint)

When a second provider is added, promote tavus.py to base.py with an
AvatarProvider interface. Until then, premature abstraction is bloat.
"""

from app.avatar.tavus import tavus_status, get_tavus_config, TavusConfig

__all__ = ["tavus_status", "get_tavus_config", "TavusConfig"]
