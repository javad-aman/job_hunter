"""Title-based pre-filter: skip LLM scoring for obvious non-matches.

Mirrors the hard rules in the scorer prompt so we don't burn API calls
on postings the model would score 0–25 anyway.
"""

from __future__ import annotations

import logging

from jobhunt.models import Posting

logger = logging.getLogger(__name__)

_SKIP_TITLE_KEYWORDS = [
    "software engineer",
    "swe",
    "data engineer",
    "ml engineer",
    "ai engineer",
    "machine learning engineer",
    "hardware engineer",
    "devops",
    "backend engineer",
    "frontend engineer",
    "full stack engineer",
    "fullstack engineer",
    "full-stack engineer",
    "site reliability",
    "sre ",
    "data scientist",
    "data analyst",
    "business analyst",
    "product manager",
    "program manager",
    "project manager",
    "scrum master",
    "solutions architect",
    "sales engineer",
    "account executive",
    "account manager",
    "recruiter",
    "hr ",
    "human resources",
    "marketing manager",
    "content strategist",
    "copywriter",
    "seo ",
]


def prefilter(postings: list[Posting]) -> tuple[list[Posting], list[Posting]]:
    """Return (to_score, skipped).

    Skipped postings get score=0 and a reason so they still appear in
    logs but never reach the LLM.
    """
    to_score: list[Posting] = []
    skipped: list[Posting] = []

    for p in postings:
        title_lower = p.title.lower()
        if any(kw in title_lower for kw in _SKIP_TITLE_KEYWORDS):
            p.score = 0
            p.reasons = ["title pre-filter: non-design role"]
            p.red_flags = []
            skipped.append(p)
        else:
            to_score.append(p)

    if skipped:
        logger.info("Pre-filter skipped %d postings (non-design titles)", len(skipped))

    return to_score, skipped
