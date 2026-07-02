# Provider Registry And Integration Notes

Use this file when selecting market-data, fundamentals, events, fund-flow, or search providers for an A-share HTML report.

## Researched Skill/Project Patterns

| Source | What to borrow | Local integration decision |
| --- | --- | --- |
| `xticktop/skills` | Token-authenticated API for A shares, HK stocks, ETFs, indices, convertible bonds, real-time/minute/daily K-lines, financial data, hot money, market emotion, concept data, quant factors, and 50+ indicators. | Vendor skill is copied locally under `xtick/`. `xtick/scripts/Config.py` reads `XTICK_TOKEN` first and falls back to the local configured token. Use XTick as Tier-1 source when token is present. |
| `xticktop/DemoXtickPython` | REST endpoints and examples: `/doc/stockinfo`, `/doc/kline/market`, `/doc/order/five`, hot data, indicators. | Use direct HTTP adapters in `backend/app/source_registry.py`; only call vendor scripts for debugging. |
| ClawHub `a-share-real-time-data` | `mootdx`/TDX access pattern for K-lines, realtime quotes, and tick transactions; pure six-digit TDX code conversion; Beijing Stock Exchange unsupported. | Add as Tier-2 fallback for realtime quotes and historical bars when dependency is installed. Filter `.BJ` before mootdx. |
| ClawHub `equal-data-skill` | Broad event/fundamental/institution data: realtime quotes, historical K, announcements, news, SW industries, index constituents, institutional holdings, fund movements, insider changes, unlocks, block trades, LHB. | Add `EQUAL_DATA_API_KEY` to env contract; use as Tier-1 event and institution source when configured. |
| `shaoxing-xie/openclaw-data-china-stock` | Multi-source automatic degradation: AkShare, Sina, Eastmoney, Tushare, plus tool/skill split and evidence-constrained output. | Adopt provider probe + fallback registry. Do not bind report logic to one upstream. |
| `simonlin1212/a-stock-data` | Direct HTTP endpoints, no heavy wrapper dependency, throttled Eastmoney calls, TDX fallback, CNINFO mapping, industry/stock research, ETF options, sentiment/hot lists. | Use direct HTTP where stable; add throttling and source audit for Eastmoney/THS/Sina; keep AkShare optional rather than mandatory. |
| `liusai0820/Stock-Analysis-Skill` | Market-aware code parsing and data-source degradation: Tushare -> efinance -> AkShare -> yfinance; search fallback chain. | Reuse routing idea; adapt for A-share-first HTML reports. |
| `molezzz/openclaw-stock-skill` | Feature grouping: realtime market, intraday volume, money flow, fundamentals, sector ranking, HK/fund/convertible bond support. | Extend report prompt coverage and future `Pipeline` report ids along the same domains. |

## Provider Tiers

| Tier | Provider | Environment/config | Best for | Fallback notes |
| --- | --- | --- | --- | --- |
| 1 | XTick | `XTICK_TOKEN` or `xtick/scripts/Config.py` | Realtime quote, minute/day K, index/ETF/HK/convertible bond, hot money, concepts, market emotion, indicators, factors. | Respect permission tier. Record missing fields if endpoint returns no data. |
| 1 | Tushare Pro | `TUSHARE_TOKEN` | Trading calendar, stock master, daily bars, fundamentals, money flow, unlocks, index/industry data. | Optional dependency; slower for realtime. |
| 1 | Equal Data | `EQUAL_DATA_API_KEY` | Events, announcements, institutional holdings, LHB, insider changes, unlocks, SW industry, index constituents. | Paid/API-key source; do not call if not configured. |
| 2 | AkShare | optional package | Broad free A-share, fund, macro, finance tables. | Field names change often; defensive adapters required. |
| 2 | mootdx/TDX | optional package | Realtime quote, K-line, tick transaction fallback. | No Beijing Stock Exchange support; convert `000001.SZ` -> `000001`. |
| 2 | efinance | optional package | Eastmoney-backed quote/fund/ETF data with a Python wrapper. | Watch for upstream throttling. |
| 3 | Sina direct HTTP | built-in `httpx` | Index realtime quote, ETF/option snippets, low-friction verification. | GBK response; use finance referer. |
| 3 | Eastmoney direct HTTP | built-in `httpx` | Sector/theme, fund-flow, hot lists, announcements, research links. | Add session reuse, random delay, retries, and source audit. |
| 3 | THS direct HTML | built-in `httpx` | Industry/concept ranking, industry net inflow, top gainers/decliners. | GBK response; layout can change. |
| 3 | CNINFO/SSE/SZSE/BSE | built-in `httpx` | Official announcements, exchange notices, regulator documents. | Prefer official source for event risk. |
| Search | Tavily | `TAVILY_API_KEY` | Fresh web/news search. | First search choice when configured. |
| Search | Serper | `SERPER_API_KEY` | Google-news style search. | Good web search fallback. |
| Search | SerpAPI | `SERPAPI_API_KEY` | Google News API. | Added to `SearchHub`. |
| Search | Brave | `BRAVE_API_KEY` | Independent web/news index. | Added to `SearchHub`. |
| Search | SearxNG | `SEARXNG_URL` | Self-hosted meta-search. | Last configured fallback. |

## Canonical Routing By Report

| Report/function | Primary sources | Fallback chain |
| --- | --- | --- |
| `market_replay` | XTick realtime + THS industry + Sina indices + SearchHub | Sina/THS direct -> AkShare/Eastmoney -> demo with explicit warning |
| `quant_factor` | XTick indicators/factors + Tushare/AK daily bars | local pandas indicators from Sina/TDX bars |
| `sector_stock` | XTick concepts + Equal Data/SW industry + THS/Eastmoney constituents | AkShare sector constituents -> user-provided list |
| `sector_flow_rotation` | XTick hot money + THS/Eastmoney industry net flow | AkShare fund-flow proxy |
| `smart_money_clusters` | XTick LHB/market emotion + Equal Data LHB/institution data | Eastmoney LHB + THS hot lists |
| `sector_valuation_diagnosis` | Equal Data/Tushare fundamentals + XTick quote | AkShare/CNINFO announcements + Eastmoney valuation |
| `trend_resonance` | XTick K-line + indicators + Sina/TDX fallback bars | local indicator computation |
| `watchlist_terminal` | XTick realtime quote + news SearchHub + CNINFO | Sina quote + THS/Eastmoney pages |
| `index_etf_monitor` | XTick index/ETF + Sina index/ETF | Eastmoney ETF lists |
| `liquidity_dashboard` | Tushare/Equal Data + Eastmoney northbound/margin/ETF flow | official exchange + public pages |
| `earnings_catalyst_calendar` | Equal Data/Tushare/CNINFO | exchange pages + SearchHub |
| `single_stock_event_risk` | Equal Data events + CNINFO + SearchHub | official announcements first, web search second |
| `industry_chain_map` | Equal Data/SW industry + Eastmoney/THS concepts + SearchHub | manual taxonomy with source audit |
| `global_mapping` | SearchHub + Sina/HK/US quote providers + XTick HK | yfinance/finance pages |

## Implementation Hooks

- `backend/app/source_registry.py`
  - `XTickClient.stock_info(symbol)`
  - `XTickClient.kline_market(code, start_date, end_date, asset_type=1, fq=1, period="1d")`
  - `SinaQuoteClient.index_quotes()`
  - `ThsClient.industry_rank()`
  - `probe_sources(include_samples=False)`
- `scripts/probe_data_sources.py`
  - `python scripts/probe_data_sources.py`
  - `python scripts/probe_data_sources.py --samples`
- `backend/app/main.py`
  - `SearchHub` now supports Tavily -> Serper -> SerpAPI -> Brave -> SearxNG.

## Audit Requirements

Every generated HTML report should include:

- provider used by data category;
- data date and retrieval timestamp;
- field definitions and proxy formulas;
- missing fields and confidence impact;
- source conflicts and chosen resolution;
- third-party API permission limitations.

Never print or persist API tokens inside reports. If a token is configured in a local file, keep that file ignored by Git.
