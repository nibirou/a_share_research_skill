# HTML Report Data Matrix

Use this file before generating or changing any HTML report. Its purpose is to make every page data-driven: identify the required fields first, call the highest-quality available provider, then degrade field by field instead of leaving large empty UI blocks.

## Provider Ladder

| Priority | Provider/channel | Use first for | Current local status |
| --- | --- | --- | --- |
| P0 institutional | Wind/iFind/local licensed data lake | production-grade constituents, estimates, fund ownership, northbound breakdown, industry taxonomy | not bundled; keep as future enterprise adapter |
| P1 configured API | XTick | A-share/index/ETF/HK master data, realtime/day/minute bars, market emotion, hot money, news, quant data, indicators | implemented through `XTickClient`; token read from env or local config |
| P1 configured API | Tushare Pro | trading calendar, daily bars, daily_basic, financial statements, disclosure calendar, money flow, limit-up/down, margin, HSGT, pledge, unlock | generic HTTP client implemented; token optional and currently not required for fallback pages |
| P1 configured API | Equal Data / kjiujing | A-share realtime/history, funds/indices, financial reports, insider changes, institutional holdings, LHB | documented/env reserved; adapter still pending |
| P2 optional Python | AkShare | broad A/HK/US/fund/futures/macro tables, Eastmoney-backed spot/industry/funds, financial tables | documented; dependency not required by base install |
| P2 optional Python | mootdx | no-key TDX realtime, K-line, tick transaction fallback | documented; useful when Eastmoney/THS throttles |
| P2 optional Python | efinance/yfinance/baostock | Eastmoney wrapper, Yahoo global quotes, free daily history | documented; optional |
| P3 direct HTTP | Tencent | A-share realtime quote, PE/PB, market cap, turnover, limit-up/down prices | implemented through `TencentQuoteClient`; useful when Eastmoney quote endpoints throttle |
| P3 direct HTTP | Eastmoney | all-A quotes, industry/concept rankings, board constituents, ETF list, main-force fund-flow proxy, LHB, institution seats, margin, northbound turnover, unlocks, executive changes, fund holdings | implemented through `EastmoneyClient` |
| P3 direct HTTP | Eastmoney push2his/push2ex | stock fund-flow history windows; limit-up, break-board, down-limit, yesterday-limit pools | implemented; public but rate-sensitive, so cache/retry/throttle and disclose missing windows |
| P3 direct HTTP | DangInvest | news, industry/sub-industry/concept summary and board detail | implemented through `DangInvestClient`; use as board heat/constituent fallback and cross-check |
| P3 static JSON | hhxg.top | market snapshot, hot themes, limit-up ladder, hot-money summary, calendar/unlock/earnings events | implemented through `HhxgClient`; audit date freshness |
| P3 direct HTTP | Sina | A-share index quote, HK/US/global/FX/commodity quote snippets, A-share financial three statements | implemented through `SinaQuoteClient`, `SinaGlobalClient`, and `SinaFinanceClient` |
| P3 direct HTTP | THS | industry breadth, industry rise/fall, industry fund-flow proxy, industry constituents fallback | implemented through `ThsClient` |
| P3 official public | CNINFO / exchanges / regulators | announcements, investor Q&A, disclosure PDFs, event confirmation, exchange margin fallback | implemented for CNINFO announcement search, CNINFO IRM plus SSE/SZSE margin; PDF parsing pending |
| Search | Tavily / Serper / SerpAPI / Brave / SearxNG | fresh policy, news, research links, cross-checking | routed in `SearchHub` when keys/URLs are configured |

## Page-Level Requirements

| Report id | Core data needed by the page | Primary channel | Fallback chain | Current implementation and gaps |
| --- | --- | --- | --- | --- |
| `market_replay` | major index quotes, A-share breadth, limit-up/down count, sector rise/fall, sector fund flow, top events/news, risk summary | Sina/Tencent quotes + Eastmoney/THS sectors + Eastmoney push2ex + hhxg snapshot + SearchHub | DangInvest news/boards, AkShare/mootdx quotes, official news/search | original renderer plus source registry. Missing: northbound minute split, margin daily delta, official policy event tagging |
| `quant_factor` | index OHLCV, momentum/reversal, turnover, breadth, limit-up emotion, fund-flow factors, composite timing score | XTick quant data/indicators + Tushare daily/daily_basic | local pandas indicators from Eastmoney/Sina/mootdx bars; AkShare daily bars | XTick probe available; full factor backfill and historical factor cache still pending |
| `sector_stock` | target sector aliases, constituents, quote, pct change, turnover, float cap, PE/PB, 3D/5D/20D fund-flow proxy, leader/laggard, stock event notes | Eastmoney board search/constituents + Eastmoney push2his fund-flow windows + CNINFO announcements | THS constituents, DangInvest board detail, Tencent quote, AkShare sector constituents, XTick if permitted, user-provided list | target board constituents, CNINFO, Sina finance, and push2his windows now implemented. Missing: multi-taxonomy reconciliation and business-purity scoring |
| `sector_flow_rotation` | industry/concept ranking, 1D/3D/5D/20D fund-flow, breadth, ETF confirmation, six-month catalyst map | Eastmoney/THS/DangInvest board heat + Eastmoney push2his and sector flows + hhxg themes | AkShare sector fund-flow, efinance wrapper, XTick if permitted, manual event search | direct Eastmoney/THS/DangInvest/hhxg fills first layers. Remaining: sector-level long-window history needs broader cache/backfill |
| `smart_money_clusters` | smart-money inflow clusters, limit-up emotion, LHB/institution seats, block trades, high-conviction attack width | Eastmoney push2ex limit pools + Eastmoney LHB/institution trades/seats + hhxg ladder/hot-money | THS hot concepts, XTick/Equal Data/Tushare if permitted, AkShare big-deal tables | free LHB/seat/limit-pool fallback implemented. Missing: unique broker-seat identity graph and block trades |
| `sector_valuation_diagnosis` | constituent PE/PB/PS, market cap, revenue/profit growth, ROE, margin, cash flow, valuation percentile, announcement catalysts | Tushare/Equal Data fundamentals + Eastmoney valuation + CNINFO | Sina financial three statements; CNINFO report PDFs; SearchHub | Eastmoney PE/PB/market cap, CNINFO events, and Sina three-statement snapshots fill the first layer. Missing: valuation percentile history and revenue mix |
| `trend_resonance` | sector trend, constituent MA/RSI/MACD/volatility, index/sector/stock resonance, divergence list | XTick K-line/indicators | mootdx/AkShare bars + local indicator calculation | prompt and generic renderer active. Missing: per-stock historical K-line batch and local indicator cache |
| `watchlist_terminal` | user watchlist quote, ranking, fund-flow, news, announcements, risk flags, notes | Tencent/Eastmoney realtime + Eastmoney push2his + CNINFO announcements/IRM + SearchHub | Sina/TDX quote, AkShare/efinance, user-supplied snapshot | generic context active; stock-code-specific CNINFO and IRM work. Missing: persistent watchlist import/export and per-stock news dedup |
| `index_etf_monitor` | broad/narrow index quotes, ETF quote/volume/flow, premium/discount if available, style rotation | XTick index/ETF master + Eastmoney ETF rank + Sina index | AkShare ETF/fund tables; yfinance for offshore ETFs | Eastmoney ETF and XTick ETF count implemented. Missing: ETF shares/creation-redemption and premium/discount |
| `liquidity_dashboard` | turnover, all-A amount, northbound, margin financing, ETF flow, repo/SHIBOR, FX, market emotion | Eastmoney all-A/ETF/margin/northbound + SSE/SZSE official margin + Sina FX + hhxg snapshot | Tushare/Equal Data if configured + AkShare macro/money market | market turnover, margin balance, northbound turnover, ETF, FX and emotion proxies implemented. Missing: repo/SHIBOR and ETF share changes |
| `earnings_catalyst_calendar` | earnings disclosure dates, pre-announcements, guidance, shareholder meetings, policy/product catalysts | CNINFO announcements + hhxg earnings/unlock calendar + Eastmoney unlock/executive changes + SearchHub | Tushare disclosure calendar if configured + exchange calendars + AkShare calendar + official ministry pages | CNINFO, hhxg calendar, Eastmoney unlocks and executive changes implemented. Missing: formal exchange disclosure-calendar adapter |
| `single_stock_event_risk` | stock quote, valuation, fund-flow, recent announcements, reduction/unlock/pledge/legal risk, news sentiment | CNINFO announcements/IRM + Eastmoney unlock/executive changes + Tencent/Eastmoney quote | Equal Data/Tushare if configured + exchange pages + official-site search | CNINFO stock-code search/IRM, unlocks and executive changes implemented. Missing: pledge/litigation structured extraction |
| `industry_chain_map` | upstream/midstream/downstream taxonomy, price drivers, beneficiary stocks, cost transmission, related concepts/ETFs | Equal Data/SW taxonomy + Eastmoney/THS concepts + SearchHub | AkShare concept/industry tables, manual taxonomy with audit | concept/industry/ETF data available. Missing: structured industry-chain ontology and commodity price feeds beyond Sina snippets |
| `global_mapping` | US/HK/global indices, sector peers, commodities, FX, China ADR/HK leaders, transmission path to A-share themes | Sina global/HK/FX/commodity + SearchHub + XTick HK | yfinance/Stooq/Yahoo direct, Eastmoney global pages | Sina global implemented; commodity pct is neutralized when Sina lacks compatible field. Missing: peer-to-A-share mapping table and ADR basket |
| `agent_debate` | evidence pack from market, sector, stock, event, liquidity, valuation and risk modules; bull/bear/neutral conclusions | all above providers plus configured/custom LLM | local rule agents when no LLM configured | custom OpenAI-compatible model routing implemented. Missing: richer evidence graph and contradiction scoring |

## Field-Level Degradation Rules

- Quote fields degrade independently: if PE/PB is missing but price and pct change are present, still render the row and mark PE/PB as `数据缺失`.
- Fund-flow fields must show the definition. Eastmoney/THS main-force net inflow is a proxy and is not equivalent to proprietary "super capital" unless the provider explicitly documents that field.
- For sector constituents, prefer a board code resolved by Eastmoney search (`BKxxxx`) or a taxonomy owner. If the sector name cannot be resolved, fall back to THS/AkShare/user list and disclose the source.
- Eastmoney `clist` responses should be cached locally. If Eastmoney throttles or closes connections, reuse the latest matching cache and mark the report as using cached data.
- Eastmoney `push2his` historical fund-flow can disconnect after burst requests. Use low concurrency, retry, local cache, and optional AkShare/efinance wrappers if installed before degrading to 1D proxy.
- Limit-up/down emotion should use Eastmoney `push2ex` first, then AkShare/THS/hhxg, then XTick/Tushare if permission exists.
- For announcements, search CNINFO by exact stock code first. If a sector keyword has no results, query the top sector constituents and deduplicate by URL/title.
- For investor-rumor/event verification, query CNINFO IRM after announcements and clearly label investor Q&A as company reply evidence, not audited financial disclosure.
- For global/commodity data, never display a numeric percent change unless the provider payload position is verified for that asset class.
- If a configured P1 source fails, keep the P3 public result visible but lower confidence and record the failure in the data audit section.

## Immediate Backlog

1. Add optional `AkShareClient` wrappers without making AkShare a hard dependency; priority functions: stock/sector historical fund flow, macro/liquidity tables, ETF shares, repo/SHIBOR, block trades.
2. Add optional `MootdxClient` and `BaostockClient` for no-key quote/K-line/fundamental fallback when direct HTTP providers throttle.
3. Add local evidence cache so repeated `--all` generation reuses the same retrieval snapshot and avoids provider throttling.
4. Add Tushare endpoint shortcuts on top of the generic HTTP client for users who configure a token.
5. Add `EqualDataClient` only after API key and docs are configured; remaining priority endpoints: pledge/litigation, complete event taxonomy, valuation percentile, revenue mix/business purity.
