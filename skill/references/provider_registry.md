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

## 2026-07-02 Additional Search Findings

| Source | Data capability observed | Local adoption |
| --- | --- | --- |
| `succ985/openclaw-akshare-skill` | AkShare-backed A-share, HK, US, futures, funds, macro; examples include `stock_zh_a_spot_em` and `stock_zh_a_hist`. | Keep AkShare optional; use only through defensive adapters because field names and upstream pages change. |
| `waditu-tushare/skills` | Official Tushare skill; 220+ financial endpoints and 235+ API markdown docs, token-based. | Added generic direct HTTP `TushareHttpClient`; add endpoint shortcuts when `TUSHARE_TOKEN` is configured. |
| `openstockdata/stock-data-skill` | 47 tools covering A shares, HK, US and crypto with multi-source failover; includes stock price, realtime, chip, fund flow, global news, and source health. | Borrow health-check and failover style; do not add as dependency. |
| `HKUDS/Vibe-Trading` | Data-loader registry with no-key fallbacks: yfinance for HK/US, OKX/ccxt for crypto, mootdx for A shares, AKShare as broad backup; optional Tushare. | Reinforces no-key fallback chain: direct HTTP -> mootdx/AkShare -> configured APIs. |
| `rollysys/use_cninfo` | CNINFO `hisAnnouncement/query`, PDF download, PyMuPDF markdown extraction, local cache, announcement classification. | Implemented lightweight CNINFO search now; full PDF parse/cache is a next step for event-risk pages. |
| `kooui/china-stocks-daily-review` on ClawHub | Explicit 3-tier degradation: Tushare primary -> AKShare secondary -> search fallback; each data item degrades independently. | Adopted field-level degradation and visible missing-data audit. |
| `zack995/zack995-akshare` on ClawHub | Treats AKShare as broad Chinese market and macro-finance source for A/HK/US/ETF/fund/index/macro/rates/bonds/futures. | Add to optional source backlog for macro/liquidity and broad table fallback. |
| `openclaw/clawhub` Equal Data issue | Documents kjiujing/equal-data style coverage: realtime/history, funds/indices, financial reports, insider changes, institutional holdings, LHB. | Keep `EQUAL_DATA_API_KEY` contract and prioritize an adapter once docs/key are available. |

See `references/report_data_matrix.md` for page-by-page field requirements and fallback chains.
See `references/external_free_sources_review.md` for the full 2026-07-03 review of the 16 user-provided GitHub projects.

## Provider Tiers

| Tier | Provider | Environment/config | Best for | Fallback notes |
| --- | --- | --- | --- | --- |
| 1 | XTick | `XTICK_TOKEN` or `xtick/scripts/Config.py` | Realtime quote, minute/day K, index/ETF/HK/convertible bond, hot money, concepts, market emotion, indicators, factors. | Respect permission tier. Record missing fields if endpoint returns no data. |
| 1 | Tushare Pro | `TUSHARE_TOKEN` | Trading calendar, stock master, daily bars, fundamentals, money flow, unlocks, index/industry data. | Optional dependency; slower for realtime. |
| 1 | Equal Data | `EQUAL_DATA_API_KEY` | Events, announcements, institutional holdings, LHB, insider changes, unlocks, SW industry, index constituents. | Paid/API-key source; do not call if not configured. |
| 2 | AkShare | optional package | Broad free A-share, fund, macro, finance tables. | Field names change often; defensive adapters required. |
| 2 | mootdx/TDX | optional package | Realtime quote, K-line, tick transaction fallback. | No Beijing Stock Exchange support; convert `000001.SZ` -> `000001`. |
| 2 | efinance | optional package | Eastmoney-backed quote/fund/ETF data with a Python wrapper. | Watch for upstream throttling. |
| 3 | Tencent direct HTTP | built-in `httpx` | A-share realtime quote, PE/PB, market cap, turnover, limit-up/down prices. | Prefer for quote fallback on residential networks; endpoint is `qt.gtimg.cn`. |
| 3 | Sina direct HTTP | built-in `httpx` | Index realtime quote, global/HK/FX/commodity snippets, A-share financial three statements. | GBK/JSON mixed response; use finance referer. |
| 3 | Eastmoney direct HTTP | built-in `httpx` | All-A quotes, sector/theme, board constituents, ETF list, 1D and 3D/5D/20D fund-flow proxy, limit-up/break-board/down-limit pools, LHB, institution seats, margin, northbound, unlocks, executive hold changes, institutional/fund holdings. | Implemented with multi-domain retries, datacenter pagination, and local JSON cache; `push2his`/`push2ex` can throttle, so record proxy definitions and missing-window impact. |
| 3 | THS direct HTML | built-in `httpx` | Industry/concept ranking, industry net inflow, top gainers/decliners, industry constituents fallback. | GBK response; layout can change; Ajax pagination may 401, so use ordinary detail pages when available. |
| 3 | DangInvest direct HTTP | built-in `httpx` | 7x24 market news, industry/sub-industry/concept heatmap, board constituents. | Useful fallback for sector heat and constituents; check `tradeDate`/`asOf`. |
| 3 | hhxg static JSON | built-in `httpx` | Daily market snapshot, sentiment, hot themes, limit-up ladder, hot-money summary, sector funds, trading calendar, unlock/earnings/delivery events. | Pre-aggregated latest trading-day data; always audit date freshness. |
| 3 | CNINFO/SSE/SZSE/BSE | built-in `httpx` | Official announcements, investor Q&A, exchange notices, regulator documents, exchange margin fallback. | CNINFO search, CNINFO IRM, SSE margin, and SZSE margin latest-date fallback are implemented; PDF parsing remains pending. |
| Search | Tavily | `TAVILY_API_KEY` | Fresh web/news search. | First search choice when configured. |
| Search | Serper | `SERPER_API_KEY` | Google-news style search. | Good web search fallback. |
| Search | SerpAPI | `SERPAPI_API_KEY` | Google News API. | Added to `SearchHub`. |
| Search | Brave | `BRAVE_API_KEY` | Independent web/news index. | Added to `SearchHub`. |
| Search | SearxNG | `SEARXNG_URL` | Self-hosted meta-search. | Last configured fallback. |

## Canonical Routing By Report

| Report/function | Primary sources | Fallback chain |
| --- | --- | --- |
| `market_replay` | Sina/Tencent quotes + Eastmoney/THS sectors + hhxg snapshot + SearchHub | DangInvest news/boards -> AkShare/mootdx -> demo with explicit warning |
| `quant_factor` | XTick indicators/factors + Tushare/AK daily bars | local pandas indicators from Sina/TDX bars |
| `sector_stock` | Eastmoney board search/constituents + Eastmoney push2his fund-flow windows + CNINFO announcements | THS constituents -> DangInvest board detail -> AkShare sector constituents -> user-provided list |
| `sector_flow_rotation` | Eastmoney/THS/DangInvest industry-concept heat + Eastmoney push2his/sector flows + hhxg themes | AkShare sector fund-flow -> XTick hot money if permitted -> manual event search |
| `smart_money_clusters` | Eastmoney push2ex limit pools + Eastmoney LHB/institution seats + hhxg hot-money/ladder | THS hot lists -> XTick/Equal Data if permitted |
| `sector_valuation_diagnosis` | Equal Data/Tushare fundamentals + XTick quote | Sina financial three statements + CNINFO announcements + Eastmoney valuation |
| `trend_resonance` | XTick K-line + indicators + Sina/TDX fallback bars | local indicator computation |
| `watchlist_terminal` | Tencent/Eastmoney realtime quote + CNINFO announcements/IRM + SearchHub | Sina quote + THS/Eastmoney pages + optional mootdx |
| `index_etf_monitor` | XTick index/ETF + Sina index/ETF | Eastmoney ETF lists |
| `liquidity_dashboard` | Eastmoney northbound/margin/ETF flow + SSE/SZSE official margin + Sina FX + hhxg calendar | Tushare/Equal Data if configured + AkShare macro/money-market |
| `earnings_catalyst_calendar` | CNINFO announcements + hhxg earnings/unlock calendar + Eastmoney unlock/executive changes | Tushare disclosure calendar if configured + exchange pages + SearchHub |
| `single_stock_event_risk` | CNINFO announcements/IRM + Eastmoney unlock/executive changes + Tencent/Eastmoney quote | Equal Data/Tushare if configured + official-site search |
| `industry_chain_map` | Equal Data/SW industry + Eastmoney/THS concepts + SearchHub | manual taxonomy with source audit |
| `global_mapping` | SearchHub + Sina/HK/US quote providers + XTick HK | yfinance/finance pages |

## Implementation Hooks

- `backend/app/source_registry.py`
  - `XTickClient.stock_info(symbol)`
  - `XTickClient.kline_market(code, start_date, end_date, asset_type=1, fq=1, period="1d")`
  - `XTickClient.market_emotion(trade_date)`
  - `XTickClient.money_flow(code, start_date, end_date, asset_type=1)`
  - `XTickClient.news(trade_date, minutes=0)`
  - `XTickClient.quant_data_realtime(field="all", asset_type=1)`
  - `SinaQuoteClient.index_quotes()`
  - `TencentQuoteClient.quotes(codes)`
  - `SinaGlobalClient.quotes()`
  - `ThsClient.industry_rank()`
  - `ThsClient.industry_constituents_by_name(name, limit)`
  - `EastmoneyClient.a_spot(limit)`
  - `EastmoneyClient.industry_rank(limit)`
  - `EastmoneyClient.concept_rank(limit)`
  - `EastmoneyClient.etf_rank(limit)`
  - `EastmoneyClient.board_constituents_by_name(name, limit)`
  - `EastmoneyClient.stock_fund_flow_history(code, limit)`
  - `EastmoneyClient.stock_fund_flow_windows(code, float_mv_yi)`
  - `EastmoneyClient.limit_up_pool(date, limit)`
  - `EastmoneyClient.break_limit_pool(date, limit)`
  - `EastmoneyClient.limit_down_pool(date, limit)`
  - `EastmoneyClient.yesterday_limit_pool(date, limit)`
  - `EastmoneyClient.datacenter(report_name, ...)`
  - `EastmoneyClient.lhb_daily(start_date, end_date, limit)`
  - `EastmoneyClient.lhb_institution_trades(start_date, end_date, limit)`
  - `EastmoneyClient.lhb_institution_seats(cycle, limit)`
  - `EastmoneyClient.margin_account(limit)`
  - `EastmoneyClient.northbound_deal_history(limit)`
  - `EastmoneyClient.restricted_release(start_date, end_date, limit)`
  - `EastmoneyClient.executive_hold_changes(limit)`
  - `EastmoneyClient.fund_holdings(date, org_type, limit)`
  - `SinaFinanceClient.financial_snapshot(code, limit_reports)`
  - `ExchangeMarginClient.sse_summary(start_date, end_date)`
  - `ExchangeMarginClient.szse_summary(date)`
  - `CninfoClient.announcements(keyword, stock_code, days, limit)`
  - `CninfoClient.irm_questions(code, page_size, page_num)`
  - `DangInvestClient.market_news(limit, offset)`
  - `DangInvestClient.boards_summary(mode, sort, limit)`
  - `DangInvestClient.boards_detail(mode, group_key, sort, limit, offset)`
  - `HhxgClient.snapshot()`
  - `HhxgClient.trading_days(year)`
  - `HhxgClient.calendar_events(kind, month)`
  - `TushareHttpClient.request(api_name, params, fields)`
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
