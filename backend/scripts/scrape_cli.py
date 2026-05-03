"""Standalone scraper test runner.

Usage:
    cd backend
    python -m scripts.scrape_cli "coffee shops" "Austin, TX" --max 15
    python -m scripts.scrape_cli "marketing agency" "Toronto" --max 20 --no-headless --out leads.json
"""
import argparse
import asyncio
import json
import logging
import sys

from app.scraper.runner import run_scrape
from app.scraper.types import ScrapeRequest


async def _main() -> int:
    p = argparse.ArgumentParser(description="Flux Phase-3 scraper smoke test")
    p.add_argument("niche", help='e.g. "marketing agency"')
    p.add_argument("location", help='e.g. "Austin, TX"')
    p.add_argument("--max", type=int, default=15, dest="max_results")
    p.add_argument("--min-score", type=int, default=35)
    p.add_argument("--no-headless", action="store_true")
    p.add_argument("--out", help="Write JSON to this path; default stdout")
    p.add_argument("--include-dropped", action="store_true", help="Include rejected leads in output")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    req = ScrapeRequest(
        niche=args.niche,
        location=args.location,
        max_results=args.max_results,
        headless=not args.no_headless,
        min_quality_score=args.min_score,
    )

    result = await run_scrape(req)
    payload = {
        "request": {
            "niche": req.niche,
            "location": req.location,
            "max_results": req.max_results,
            "min_quality_score": req.min_quality_score,
        },
        "raw_count": result["raw_count"],
        "kept_count": result["kept_count"],
        "dropped_count": result["dropped_count"],
        "leads": [lead.to_dict() for lead in result["kept"]],
    }
    if args.include_dropped:
        payload["dropped"] = [lead.to_dict() for lead in result["dropped"]]

    text = json.dumps(payload, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {len(result['kept'])} kept leads to {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
