"""Command-line runner for the same steps the web app uses.

  python scripts/run_pipeline.py setup                              create dataset + tables
  python scripts/run_pipeline.py parse gs://BUCKET/2026/Source/file.pdf
  python scripts/run_pipeline.py parse-all --year 2026              every PDF under gs://BUCKET/2026/
  python scripts/run_pipeline.py after --year 2026                  steps 2-5 (consolidate .. compare)
  python scripts/run_pipeline.py load-reference --csv ref.csv --year 2026
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    p = sub.add_parser("parse"); p.add_argument("uri")
    p = sub.add_parser("parse-all"); p.add_argument("--year", type=int, default=config.DEFAULT_YEAR)
    p = sub.add_parser("after"); p.add_argument("--year", type=int, default=config.DEFAULT_YEAR)
    p.add_argument("--no-compare", action="store_true")
    p = sub.add_parser("load-reference"); p.add_argument("--csv", required=True)
    p.add_argument("--year", type=int, default=config.DEFAULT_YEAR)
    args = ap.parse_args()

    from pipeline import orchestrator, store

    if args.cmd == "setup":
        store.ensure_tables()
    elif args.cmd == "parse":
        if not args.uri.startswith("gs://"):
            ap.error("uri must look like gs://bucket/path/file.pdf")
        bucket, _, name = args.uri[5:].partition("/")
        print(json.dumps(orchestrator.process_document(bucket, name), indent=2))
    elif args.cmd == "parse-all":
        from pipeline.clients import gcs_client

        failures = 0
        for blob in gcs_client().list_blobs(config.GCS_BUCKET, prefix=f"{args.year}/"):
            if not blob.name.lower().endswith(".pdf"):
                continue
            try:
                print(json.dumps(orchestrator.process_document(config.GCS_BUCKET, blob.name)))
            except Exception as exc:  # keep going; the status table has the detail
                failures += 1
                print(f"FAILED {blob.name}: {exc}", file=sys.stderr)
        print(f"done, {failures} failure(s). Now run: after --year {args.year}")
        return 1 if failures else 0
    elif args.cmd == "after":
        print(json.dumps(orchestrator.run_after_steps(args.year, with_comparison=not args.no_compare), indent=2))
    elif args.cmd == "load-reference":
        from pipeline.compare import load_reference_csv

        print(f"loaded {load_reference_csv(args.csv, args.year)} reference rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
