from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.source_registry import probe_sources  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Probe configured market-data and search providers.")
    parser.add_argument("--samples", action="store_true", help="Include small data samples in the output.")
    args = parser.parse_args()
    probes = await probe_sources(include_samples=args.samples)
    print(json.dumps([p.to_dict() for p in probes], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
