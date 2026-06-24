"""Entry point: python -m jobhunt [--no-email] [--no-boards] [--no-ats] [--location LABEL]"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("jobhunt")


async def _fetch_for_location(
    loc: dict,
    args: argparse.Namespace,
) -> list:
    """Run all fetchers for a single location entry."""
    from jobhunt.config import cfg
    from jobhunt.fetchers import fetch_boards, fetch_greenhouse, fetch_lever, fetch_ashby, fetch_adzuna

    location_str: str = loc["location"]
    is_remote: bool = loc.get("is_remote", False)
    label: str = loc.get("label", location_str)

    fetch_tasks = []

    if not args.no_boards:
        fetch_tasks.append(fetch_boards(location=location_str, is_remote=is_remote))
        if cfg.adzuna_configured():
            fetch_tasks.append(fetch_adzuna(
                app_id=cfg.adzuna_app_id,
                app_key=cfg.adzuna_app_key,
                terms=cfg.search.get("terms", ["UX designer"]),
                location=location_str,
                hours_old=cfg.search.get("hours_old", 168),
                keywords=cfg.ats_title_keywords,
            ))
        else:
            logger.info("[%s] Adzuna not configured — skipping", label)

    if not args.no_ats:
        keywords = cfg.ats_title_keywords
        for company in cfg.companies:
            ats = company.get("ats", "").lower()
            name = company.get("name", "")
            token = company.get("token", "")
            if not token or token.startswith("YOUR_"):
                logger.warning("Skipping %s — token not configured", name)
                continue
            if ats == "greenhouse":
                fetch_tasks.append(fetch_greenhouse(name, token, keywords))
            elif ats == "lever":
                fetch_tasks.append(fetch_lever(name, token, keywords))
            elif ats == "ashby":
                fetch_tasks.append(fetch_ashby(name, token, keywords))
            else:
                logger.warning("Unknown ATS type %r for %s — skipping", ats, name)

    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    postings = []
    for result in results:
        if isinstance(result, Exception):
            logger.error("[%s] Fetch task failed: %s", label, result)
        else:
            postings.extend(result)

    logger.info("[%s] Total raw postings: %d", label, len(postings))
    return postings


async def _run(args: argparse.Namespace) -> None:
    from jobhunt.config import cfg
    from jobhunt.pipeline.normalizer import normalize
    from jobhunt.pipeline.deduper import dedupe
    from jobhunt.pipeline.seen_store import SeenStore
    from jobhunt.pipeline.scorer import score_postings
    from jobhunt.output.digest import write_digest
    from jobhunt.output.email_sender import send_email

    locations = cfg.locations
    if not locations:
        logger.error("No locations defined in config.yaml — add at least one under 'locations:'")
        return

    # Filter to a single location if --location flag given
    if args.location:
        locations = [l for l in locations if l.get("label") == args.location]
        if not locations:
            logger.error("No location with label %r found in config", args.location)
            return

    db_path = cfg.data_dir / "seen_jobs.sqlite"

    for loc in locations:
        label = loc.get("label", loc["location"])
        logger.info("── Processing location: %s ──────────────────────────", label.upper())

        raw = await _fetch_for_location(loc, args)
        normalized = normalize(raw)
        deduped = dedupe(normalized)
        logger.info("[%s] After normalize+dedupe: %d postings", label, len(deduped))

        with SeenStore(db_path) as store:
            new_postings = store.filter_new(deduped)
            logger.info("[%s] New (unseen) postings: %d", label, len(new_postings))

            if not new_postings:
                logger.info("[%s] Nothing new — skipping digest", label)
                continue

            scored = await score_postings(new_postings)
            store.mark_seen(scored)

        md_path, csv_path = write_digest(scored, location_label=label)
        print(f"\n[{label}] Digest written:\n  {md_path}\n  {csv_path}")

        if not args.no_email:
            send_email(md_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="jobhunt",
        description="Aggregate, score, and digest UI/UX job postings.",
    )
    parser.add_argument("--no-email", action="store_true", help="Skip sending email digest")
    parser.add_argument("--no-boards", action="store_true", help="Skip JobSpy board scraping")
    parser.add_argument("--no-ats", action="store_true", help="Skip ATS company polling")
    parser.add_argument("--location", metavar="LABEL", help="Only run one location (e.g. dallas)")
    args = parser.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
