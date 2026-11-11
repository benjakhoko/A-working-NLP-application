"""Domain errors raised by NLP services.

Routes translate these into HTTP 503 responses instead of returning fabricated
results when a model or external provider is unavailable.
"""
from __future__ import annotations


class NLPUnavailableError(RuntimeError):
    """A required model, library or external API cannot be used."""

    def __init__(self, message: str, *, hint: str | None = None, provider: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.provider = provider
