from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.expanded_reports import EXPANDED_REPORT_IDS  # noqa: E402
from backend.app.main import Pipeline, resolve_llm_config  # noqa: E402


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument(
        "--report",
        choices=["market_replay", "quant_factor", "sector_stock", *EXPANDED_REPORT_IDS, "agent_debate"],
        default="market_replay",
    )
    parser.add_argument("--sector", default="光伏设备")
    parser.add_argument("--llm-base-url", default=None, help="OpenAI-compatible base URL, for example https://api.openai.com/v1")
    parser.add_argument("--llm-api-key", default=None, help="API key for the selected OpenAI-compatible model service")
    parser.add_argument("--llm-model", default=None, help="Model name for multi-agent LLM analysis")
    args = parser.parse_args()
    p = Pipeline(resolve_llm_config(args.llm_base_url, args.llm_api_key, args.llm_model))
    results = await p.generate_all(args.sector) if args.all else [await p.generate(args.report, args.sector)]
    for r in results:
        print(f"{r['title']}: {r['url']}")

if __name__ == "__main__":
    asyncio.run(main())
