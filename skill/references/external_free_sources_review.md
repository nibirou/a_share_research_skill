# External Free Source Review

This file records the 2026-07-03 review of user-provided A-share skills/projects. Use it together with `provider_registry.md` and `report_data_matrix.md` when adding or routing data providers.

Principle: only no-key/no-registration public channels can enter the free primary/fallback ladder. Token, paid, VIP, or permissioned services are documented as references but must not be treated as guaranteed free fallbacks.

## Reviewed Projects

| Project | Free data/source channels found | Agent or workflow ideas worth borrowing | Local adoption |
| --- | --- | --- | --- |
| `wbh604/UZI-Skill` | Mainly public A-share/HK/US data wrappers and local report pipeline; no-key positioning but source implementation varies by sub-skill. | Investor panel, school-specific lenses, bull/bear debate, trap detector, HTML memo discipline. | Borrowed workflow ideas for `agent_debate`; do not copy scoring/persona text blindly. |
| `simonlin1212/a-stock-data` | Tencent `qt.gtimg.cn`, Eastmoney `push2`/`push2his`/`push2ex`/datacenter/reportapi/search, THS hot/EPS pages, Sina financial statements/options, CNINFO announcements/IRM, Baidu quotation, mootdx. | Explicit endpoint docs, Eastmoney throttling, field-level fallback, no heavy wrapper except mootdx. | Adopted Tencent quote, Eastmoney `push2his` stock fund-flow windows, Eastmoney `push2ex` limit pools, CNINFO IRM, and reinforced Sina/CNINFO/Eastmoney adapters. |
| `gosinkx/UZI-SKILL-astock` | Tencent/Sina direct quote, Baostock, AkShare, efinance, Eastmoney with throttling. | Provider health checks, cache-first runs, data-contract tests, investor schools, trap detection. | Borrowed fallback ordering: Tencent/Sina first for quotes, Eastmoney only where unique, optional Baostock/AkShare/efinance. |
| `birdilsss-byte/stoke` | mootdx, AkShare, Tencent valuation snippets, CLS/news via AkShare. | Clear source-specific rate limits and a unified facade. | Documented optional `mootdx`/AkShare/Tencent valuation roles; current base install remains no-hard-dependency. |
| `lzwme/finance-quant-skills` | AkShare, Baostock, pywencai, tdxquant/miniqmt where installed. | Separate data-source skills from strategy/backtest skills. | Documented AkShare/Baostock as optional no-key fallbacks; pywencai requires cookie/session and is not a guaranteed free backend. |
| `BitSoulTech/BitSoulStockSkill` | Public crawler ideas plus a remote service; historical service requires website token/VIP for deeper range. | Local SQLite persistence, factor library, MoE-style factor weighting, backtest API docs. | Borrow local evidence cache/factor ideas; not adopted as free provider because core service requires token/VIP. |
| `shouldnotappearcalm/a-share-skill` | DangInvest open endpoints: market news, board summary, board detail; plus AkShare/Baostock scripts. | Simple CLI wrappers with JSON output and retry. | Adopted `DangInvestClient` for board heatmaps/constituents/news fallback. |
| `Niceck/hhxg-top-hhxg-python` | `hhxg.top/static/data`: daily snapshot, market emotion, hot themes, limit-up ladder, hot money, sectors, news, trading calendar, unlock/earnings/delivery calendar. | Pre-aggregated daily snapshot with cache and schema checks. | Adopted `HhxgClient` for market replay, liquidity/calendar, limit-up emotion, and smart-money context fallback. |
| `hssqz/plate-rotation-skill` | `duanxianxia.com` endpoints for THS/KAIPAN plate rotation, plate charts, leader persistence. | "THS = daily burst; KAIPAN = persistence strength"; parse matrix before interpretation. | Documented as sector-rotation enhancement. Not wired by default because endpoint stability/cookie posture needs more soak testing. |
| `10e9928a/ifind-data` | iFind local SDK / HTTP API. | Natural-language query and professional indicator taxonomy. | Paid/professional credentials required; not a free fallback. Keep only as enterprise tier reference. |
| `online0001/short-term-stock-picker` | AkShare `stock_zt_pool_em`, `stock_zt_pool_previous_em`, `stock_dt_pool_em`, Sina/Eastmoney/Tencent historical bars through AkShare. | Short-term factor model: limit-up gene, MA alignment, volume ratio, turnover stability. | Borrowed scoring ideas for short-term watchlists; direct Eastmoney `push2ex` now covers limit pools without requiring AkShare. |
| `saberwen1/astock-data-skill` | Large AkShare interface catalog: CNINFO IRM, CNINFO industry/profile/share changes, Baidu hot search/valuation, Sina ESG/LHB/global, Eastmoney limit pools/fund flow. | Treat AkShare docs as a discovery index, then prefer direct HTTP where stable. | Used as interface checklist; CNINFO IRM and Eastmoney limit/fund-flow are now direct adapters. |
| `1018466411/openclaw-stock-data-skill` | `data.diemeng.chat`/`mg.diemeng.chat` service with API key and permission gates. | Broad endpoint taxonomy: daily/minute, financials, main fund flow, chips, pledge, margin, sectors. | Not a free fallback. Use as endpoint taxonomy reference only. |
| `ZICXR/A-Stock-Skills` | `ifzq/gtimg`, Sina HQ, Eastmoney push2, AkShare; healthcheck-driven fallback. | Residential-IP aware provider health scoring and "skip after 3 failures". | Borrowed rule: Tencent/Sina should be quote-first on residential networks; Eastmoney requires cache/throttle. |
| `Z-AErIs/akshare-open` | AkShare wrappers for spot, history, board, fund flow, financial, index, macro, special events. | Thin CLI per function with JSON mode and timeouts. | Documented optional AkShare wrappers; not required by base install. |
| `czhh666/A-share-stock-data-skill` | mootdx, efinance, AkShare, Baostock, Yahoo, optional Tushare. | Six-source switching, technical indicators, local historical cache, JSON CLI. | Borrowed source order/caching ideas; optional dependencies stay optional. |

## New Free Channels Integrated In Code

| Channel | Adapter/function | Data now covered | Notes |
| --- | --- | --- | --- |
| Tencent quote | `TencentQuoteClient.quotes()` | A-share realtime quote, PE/PB, market cap, turnover, limit-up/down prices | Good quote fallback on residential networks. |
| Eastmoney push2his | `EastmoneyClient.stock_fund_flow_history()`, `stock_fund_flow_windows()` | 3D/5D/20D stock fund-flow proxy from daily main net inflow | Public but can throttle/disconnect after batches; uses retry/cache and lower concurrency. |
| Eastmoney push2ex | `limit_up_pool()`, `break_limit_pool()`, `limit_down_pool()`, `yesterday_limit_pool()` | Limit-up, break-board, limit-down, yesterday-limit performance | Supplies limit-up emotion and short-term pages without XTick/Tushare. |
| CNINFO IRM | `CninfoClient.irm_questions()` | Investor questions and official company replies | Useful for rumor/event-risk confirmation. |
| DangInvest | `DangInvestClient.market_news()`, `boards_summary()`, `boards_detail()` | 7x24 news, industry/sub-industry/concept heatmaps and constituents | Good fallback when Eastmoney/THS sector pages are thin. |
| hhxg.top static data | `HhxgClient.snapshot()`, `trading_days()`, `calendar_events()` | Market emotion, hot themes, ladder, hot-money snapshot, sectors, news, trading calendar, unlock/earnings/delivery events | Pre-aggregated; verify date because snapshot may be latest completed trading day. |

## Updated Fallback Rule

Do not stop at "XTick failed, Eastmoney current field failed." For every field:

1. Try no-key direct HTTP if available and field semantics are known.
2. Try optional no-key package wrappers if installed (`AkShare`, `efinance`, `mootdx`, `baostock`) and safe for the field.
3. Try configured APIs (`XTick`, `Tushare`, `Equal Data`) only when keys/permissions exist.
4. Try official announcements/search for event confirmation.
5. Render the field as missing/proxy with confidence impact only after the ladder is exhausted.

For stock fund-flow windows specifically:

```text
Eastmoney push2his daily main net inflow
-> optional AkShare/efinance Eastmoney wrappers if installed
-> XTick hot money when token permission allows
-> Eastmoney latest main net inflow / float market cap as 1D proxy
-> 数据缺失 with ranking-confidence downgrade
```
