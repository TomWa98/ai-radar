"""Command-line entry point: ``python -m ai_radar.ingest --db PATH [URL ...]``."""

import argparse
import logging
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from functools import partial
from pathlib import Path

from ai_radar.articles.repository import ArticleRepository
from ai_radar.db import open_database
from ai_radar.ingest.fetch import create_client, fetch_feed
from ai_radar.ingest.service import Fetcher, ingest_feeds


def read_feed_list(path: Path) -> list[str]:
    """Read one feed URL per line; blank lines and ``#`` comments are ignored."""
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def main(argv: Sequence[str] | None = None, fetch: Fetcher | None = None) -> int:
    """Run one ingestion pass; return 0 if every feed succeeded, else 1."""
    parser = argparse.ArgumentParser(
        prog="python -m ai_radar.ingest",
        description="Fetch RSS/Atom feeds and store new articles.",
    )
    parser.add_argument("--db", type=Path, required=True, help="SQLite database file")
    parser.add_argument(
        "--feeds-file", type=Path, help="file with one feed URL per line"
    )
    parser.add_argument("urls", nargs="*", metavar="URL", help="feed URL")
    args = parser.parse_args(argv)

    urls = list(args.urls)
    if args.feeds_file is not None:
        try:
            urls.extend(read_feed_list(args.feeds_file))
        except (OSError, UnicodeDecodeError) as exc:
            parser.error(f"cannot read feeds file: {exc}")
    urls = list(dict.fromkeys(urls))  # drop repeats, keep order
    if not urls:
        parser.error("no feed URLs given")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with ExitStack() as stack:
        conn = stack.enter_context(open_database(args.db))
        if fetch is None:
            client = stack.enter_context(create_client())
            fetch = partial(fetch_feed, client=client)
        results = ingest_feeds(urls, fetch, ArticleRepository(conn))

    for result in results:
        if result.ok:
            print(
                f"{result.url}: {result.new} new, {result.duplicates} duplicates, "
                f"{result.skipped} skipped"
            )
        else:
            print(f"{result.url}: failed: {result.error}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
