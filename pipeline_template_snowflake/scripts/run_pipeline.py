"""Command-line runner for the same steps the web app uses.

  python scripts/run_pipeline.py setup                              create schema, stage/volume and tables
  python scripts/run_pipeline.py parse 2026/Some_Source/file.pdf    one document (name relative to the storage root)
  python scripts/run_pipeline.py parse-new [--year 2026]            every PDF not parsed yet, then steps 2-5
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
    p = sub.add_parser("parse"); p.add_argument("object_name")
    p = sub.add_parser("parse-new"); p.add_argument("--year", type=int, default=None)
    p = sub.add_parser("after"); p.add_argument("--year", type=int, default=config.DEFAULT_YEAR)
    p.add_argument("--no-compare", action="store_true")
    p = sub.add_parser("load-reference"); p.add_argument("--csv", required=True)
    p.add_argument("--year", type=int, default=config.DEFAULT_YEAR)
    args = ap.parse_args()

    from pipeline import orchestrator, store

    if args.cmd == "setup":
        store.ensure_tables()
    elif args.cmd == "parse":
        print(json.dumps(orchestrator.process_document(args.object_name), indent=2))
    elif args.cmd == "parse-new":
        result = orchestrator.parse_new_files(args.year)
        print(json.dumps(result, indent=2))
        return 1 if result["failed"] else 0
    elif args.cmd == "after":
        print(json.dumps(orchestrator.run_after_steps(args.year, with_comparison=not args.no_compare), indent=2))
    elif args.cmd == "load-reference":
        from pipeline.compare import load_reference_csv

        print(f"loaded {load_reference_csv(args.csv, args.year)} reference rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
