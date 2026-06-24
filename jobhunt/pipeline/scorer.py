"""LLM scoring via Anthropic API.

Batches postings into groups, sends a single prompt per batch requesting
JSON back, then parses each result.  Falls back gracefully if the model
returns malformed JSON.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from jobhunt.config import cfg
from jobhunt.models import Posting

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _build_prompt(profile: str, batch: list[Posting]) -> str:
    listings = []
    max_chars = cfg.llm.get("description_max_chars", 3000)
    for i, p in enumerate(batch):
        desc = p.description[:max_chars] if p.description else "(no description)"
        listings.append(
            f"[{i}]\n"
            f"Title: {p.title}\n"
            f"Company: {p.company}\n"
            f"Location: {p.location}  Remote: {p.remote}\n"
            f"Description:\n{desc}"
        )

    return f"""You are a strict job-fit scorer for a UI/UX / Product Designer job search.

Candidate profile:
{profile}

Scoring rules — apply these BEFORE anything else:
- If the job title is Software Engineer, SWE, Data Engineer, ML Engineer, AI Engineer,
  Hardware Engineer, DevOps, Backend, Frontend (pure code), or any engineering-only role:
  score 0–15. Do not look for design tangents to justify a higher score.
- If the job title is Product Manager, Program Manager, Project Manager, or Operations:
  score 10–25 unless the description explicitly names UX research or design ownership.
- If the job title is Art Director or Graphic Designer with no UX/product component: score 20–35.
- Agency or consulting roles (not in-house product teams) lose 15 points.
- Roles that match title AND domain AND seniority to the candidate's profile: score 65–100.

Score each of the {len(batch)} job postings below on a 0-100 scale.
Return ONLY a JSON array with one object per posting, in the same order, each with:
  "score": integer 0-100
  "reasons": array of 1-3 short strings explaining the score
  "red_flags": array of 0-3 short strings about concerns (empty if none)

Respond with the JSON array and nothing else.

---
{"---".join(listings)}
"""


def _parse_response(text: str, batch_size: int) -> list[dict[str, Any]]:
    # Try to extract from a ```json ... ``` fence first
    fence_match = _JSON_FENCE_RE.search(text)
    candidate = fence_match.group(1) if fence_match else text.strip()

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, list) and len(parsed) == batch_size:
            return parsed
    except json.JSONDecodeError:
        pass

    # Last resort: find the first [...] in the text
    bracket_start = candidate.find("[")
    bracket_end = candidate.rfind("]")
    if bracket_start != -1 and bracket_end != -1:
        try:
            parsed = json.loads(candidate[bracket_start : bracket_end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse LLM response as JSON; applying fallback scores")
    return [{"score": 50, "reasons": ["parse error"], "red_flags": []}] * batch_size


def _apply_scores(postings: list[Posting], scores: list[dict[str, Any]]) -> None:
    for p, s in zip(postings, scores):
        p.score = max(0, min(100, int(s.get("score", 50))))
        p.reasons = [str(r) for r in s.get("reasons", [])]
        p.red_flags = [str(f) for f in s.get("red_flags", [])]


async def score_postings(postings: list[Posting]) -> list[Posting]:
    """Score all postings, mutating each Posting in-place.  Returns the list."""
    if not postings:
        return postings

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    batch_size: int = cfg.llm.get("batch_size", 10)
    model: str = cfg.llm.get("model", "claude-haiku-4-5-20251001")
    max_tokens: int = cfg.llm.get("max_tokens", 400)
    profile: str = cfg.my_profile

    for i in range(0, len(postings), batch_size):
        batch = postings[i : i + batch_size]
        prompt = _build_prompt(profile, batch)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens * len(batch),  # scale with batch
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
        except Exception as exc:
            logger.error("LLM scoring failed for batch %d: %s", i // batch_size, exc)
            # Apply neutral fallback scores
            _apply_scores(batch, [{"score": 50, "reasons": ["api error"], "red_flags": []}] * len(batch))
            continue

        scores = _parse_response(text, len(batch))
        _apply_scores(batch, scores)
        logger.info(
            "Scored batch %d/%d (%d postings)",
            i // batch_size + 1,
            (len(postings) + batch_size - 1) // batch_size,
            len(batch),
        )

    return postings
