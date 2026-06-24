"""Write the ranked digest as Markdown and CSV."""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

from jobhunt.config import cfg
from jobhunt.models import Posting

logger = logging.getLogger(__name__)


def _datestamp() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _render_markdown(postings: list[Posting], run_date: str, title_loc: str = "") -> str:
    lines: list[str] = [
        f"# Job Digest — {title_loc}{run_date}",
        f"_{len(postings)} new matches, ranked by fit score_",
        "",
    ]

    for rank, p in enumerate(postings, start=1):
        score_bar = "█" * (p.score // 10) + "░" * (10 - p.score // 10)  # type: ignore[operator]
        date_str = p.date_posted.strftime("%b %d") if p.date_posted else "?"
        remote_tag = " `remote`" if p.remote else ""

        lines += [
            f"## {rank}. [{p.title}]({p.url}) — {p.company}",
            f"**Score:** {p.score}/100  `{score_bar}`  |  "
            f"{p.location}{remote_tag}  |  posted {date_str}  |  _{p.source}_",
            "",
        ]

        if p.reasons:
            lines.append("**Why it fits:**")
            for r in p.reasons:
                lines.append(f"- {r}")
            lines.append("")

        if p.red_flags:
            lines.append("**Red flags:**")
            for f in p.red_flags:
                lines.append(f"- {f}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def write_digest(postings: list[Posting], location_label: str = "") -> tuple[Path, Path]:
    """Write Markdown and CSV digests.  Returns (md_path, csv_path)."""
    top_n: int = cfg.digest.get("top_n", 30)
    min_score: int = cfg.digest.get("min_score", 40)
    out_dir: Path = cfg.output_dir
    run_date = _datestamp()

    ranked = sorted(
        [p for p in postings if (p.score or 0) >= min_score],
        key=lambda p: p.score or 0,
        reverse=True,
    )[:top_n]

    if not ranked:
        logger.warning("No postings met the minimum score threshold (%d)", min_score)

    slug = f"{location_label}_" if location_label else ""
    md_path = out_dir / f"digest_{slug}{run_date}.md"
    title_loc = location_label.replace("_", " ").title() + " — " if location_label else ""
    md_path.write_text(_render_markdown(ranked, run_date, title_loc), encoding="utf-8")
    logger.info("Markdown digest → %s (%d postings)", md_path, len(ranked))

    csv_path = out_dir / f"digest_{slug}{run_date}.csv"
    _write_csv(ranked, csv_path)
    logger.info("CSV digest → %s", csv_path)

    return md_path, csv_path


def _write_csv(postings: list[Posting], path: Path) -> None:
    fields = [
        "rank", "score", "title", "company", "location", "remote",
        "url", "source", "date_posted", "reasons", "red_flags",
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for rank, p in enumerate(postings, start=1):
            writer.writerow({
                "rank": rank,
                "score": p.score,
                "title": p.title,
                "company": p.company,
                "location": p.location,
                "remote": p.remote,
                "url": p.url,
                "source": p.source,
                "date_posted": p.date_posted.isoformat() if p.date_posted else "",
                "reasons": " | ".join(p.reasons),
                "red_flags": " | ".join(p.red_flags),
            })
