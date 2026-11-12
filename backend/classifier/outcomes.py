"""What classification can return for an email besides a result dict."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NotJob:
    """The email isn't about a job application. by is "rules" or "ai"."""
    by: str
    detail: str = ""


@dataclass(frozen=True)
class AiPending:
    """The email is waiting in an AI batch; it is neither saved nor passed by the mail cursor."""
