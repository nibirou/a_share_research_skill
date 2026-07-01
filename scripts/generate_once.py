from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.main import Pipeline  # noqa: E402


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--report", choices=["market_replay","quant_factor","sector_stock","agent_debate"], default="market_replay")
    parser.add_argument("--sector", default="光伏设备")
    args = parser.parse_args()
    p = Pipeline()
    results = await p.generate_all(args.sector) if args.all else [await p.generate(args.report, args.sector)]
    for r in results:
        print(f"{r['title']}: {r['url']}")

if __name__ == "__main__":
    asyncio.run(main())
