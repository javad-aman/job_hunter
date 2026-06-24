from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Posting:
    """Canonical job posting — every source normalises into this shape."""

    title: str
    company: str
    location: str
    remote: bool
    url: str
    description: str
    source: str          # "indeed" | "glassdoor" | "google" | "greenhouse" | …
    date_posted: Optional[datetime] = None

    # Populated after LLM scoring
    score: Optional[int] = None
    reasons: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)

    def dedup_key(self) -> str:
        """Stable key used for URL-based deduplication."""
        return self.url.rstrip("/").lower()

    def title_company_key(self) -> str:
        """Secondary key for fuzzy title+company dedup."""
        t = self.title.lower().strip()
        c = self.company.lower().strip()
        return f"{c}||{t}"
