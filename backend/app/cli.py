"""Import episodes from the command line.

    python -m app.cli import-episodes path/to/episodes.csv
"""
import argparse
import json

from app.db import SessionLocal
from app.importer import import_episodes


def main():
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import-episodes", help="import an episodes CSV export")
    imp.add_argument("path")
    imp.add_argument("--full", action="store_true", help="print every skipped row")
    args = parser.parse_args()

    with SessionLocal() as db, open(args.path, newline="", encoding="utf-8-sig") as f:
        report = import_episodes(db, f)

    if not args.full:
        report.pop("skipped_rows")
        report.pop("warnings")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
