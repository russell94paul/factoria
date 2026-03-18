"""
prepare_demo_zip.py — Package the raw marketing data CSVs into a single zip.

Usage (from repo root):
    python scripts/prepare_demo_zip.py

Output: dist/raw_marketing_data.zip

Contains five RAW source files (raw_customers, raw_campaign_spend, raw_orders,
raw_order_items, raw_web_sessions) plus README.md. These are un-modeled source
tables; the Factoria agent workflow derives the star schema (dim_customer,
dim_campaign, fct_orders, fct_campaign_performance, fct_web_sessions) from them.

Standard library only — no third-party dependencies.
"""

import os
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR  = REPO_ROOT / "demo_data" / "raw_marketing_data"
DIST_DIR  = REPO_ROOT / "dist"
OUTPUT    = DIST_DIR / "raw_marketing_data.zip"


def main():
    if not DEMO_DIR.exists():
        print(f"ERROR: demo_data directory not found: {DEMO_DIR}", file=sys.stderr)
        sys.exit(1)

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(DEMO_DIR.iterdir())
    csv_files   = [f for f in files if f.suffix.lower() == ".csv"]
    extra_files = [f for f in files if f.suffix.lower() != ".csv"]

    if not csv_files:
        print(f"ERROR: no CSV files found in {DEMO_DIR}", file=sys.stderr)
        sys.exit(1)

    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in csv_files + extra_files:
            arcname = f"raw_marketing_data/{f.name}"
            zf.write(f, arcname)
            size_kb = f.stat().st_size / 1024
            print(f"  added {arcname}  ({size_kb:.1f} KB)")

    zip_kb = OUTPUT.stat().st_size / 1024
    print(f"\nCreated: {OUTPUT}  ({zip_kb:.1f} KB)")
    print(f"Contains {len(csv_files)} CSV file(s) + {len(extra_files)} other file(s).")


if __name__ == "__main__":
    main()
