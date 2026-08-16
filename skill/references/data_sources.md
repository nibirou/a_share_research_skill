# Data Sources And Validation

Use this reference whenever a report needs current or historical market data, fundamentals, announcements, policy/news, or fund-flow inputs.

## External Patterns Worth Borrowing

- `jwangkun/claude-for-financial-services-cn` uses a China-market tiering idea: Wind and iFind for paid professional data, AkShare as a free fallback, and China-specific industry standards such as 申万 / 中信.
- `BitSoulTech/BitSoulStockSkill` is useful as a product pattern: local SQLite persistence, multi-source realtime crawlers, 100+ factors, backtesting, and LLM-facing API documentation.
- `xticktop/skills` is useful for realtime quote coverage: 沪深京 A 股, ETF, indices, HK stocks, financial statements, and 100+ indicators.
- ClawHub `a-share-real-time-data` wraps `mootdx` for K-lines, realtime quotes, and tick transactions; remember mootdx uses six-digit TDX codes and does not support Beijing Stock Exchange codes.
- ClawHub `equal-data-skill` is a useful reference for broad A-share coverage: 5000+ listed companies, fundamentals, events, capital actions, smart money, institutional holdings, news, and announcements.
- ClawHub `tradingagents-analysis` is useful for research workflow shape: analyst team, game-theory manager, bull/bear debate, trading synthesis, and risk control.

These are architectural references. Do not install or execute third-party code inside a production workflow without code review, pinned versions, hash verification, and sandboxing.

## Provider Priority

Choose the highest available tier. Always record provider, data date, retrieval time, and field definition.

| Tier | Providers | Best for | Notes |
| --- | --- | --- | --- |
| Tier 0 paid terminal | Wind, iFind, institutional data lake | Full market data, industry classification, estimates, research, high-quality fundamentals | Prefer for production or client-facing research. |
| Tier 1 paid/API | Tushare Pro, XTick, Equal Data | A-share quotes, indices, financial statements, events, capital actions, indicators | Token required; verify rate limits and license. |
| Tier 2 free/open | AkShare, Baostock, mootdx, exchange/CNINFO pages | Open research, fallback quotes, daily bars, announcements, basic financials | Field names and availability can change. Use defensive adapters. |
| Tier 3 web/search | Eastmoney, 同花顺, Sina, Tencent, CNINFO, SSE/SZSE/BSE, official ministry sites, Tavily/Serper/SearxNG | News, policy, announcements, public quote cross-checks | Use as corroboration; avoid single-source conclusions. |

## Data Coverage Matrix

| Data need | Required fields | Preferred source | Fallback |
| --- | --- | --- | --- |
| Trading calendar | latest trading day, holiday flag | Exchange calendar / Tushare / Wind / iFind | AkShare calendar; if unavailable, mark uncertain. |
| Stock master | code, name, exchange, board, ST flag, listing status | Wind/iFind/Tushare/XTick | AkShare stock info + exchange pages. |
| Realtime quote | price, pct change, volume, turnover, high/low/open | XTick/Wind/iFind | AkShare/Eastmoney/Tencent/Sina; mootdx excludes BSE. |
| Daily bars | OHLCV, adjusted close, turnover | Wind/iFind/Tushare/XTick | AkShare/Baostock/mootdx. |
| Index breadth | up/down counts, limit ups/downs, board distribution | Wind/iFind/XTick | Eastmoney/AkShare with explicit source note. |
| Sector/theme constituents | source taxonomy, constituent list, aliases | Wind/iFind/申万/中信/同花顺/东方财富 | AkShare/website scrape; if sources conflict, disclose. |
| Fund flow | main net inflow, large-order flow, northbound, ETF flow | Wind/iFind/XTick/Equal Data | Eastmoney/THS fund-flow proxy, Eastmoney northbound turnover, AkShare; mark as proxy if needed. |
| Fundamentals | revenue, net profit, margins, ROE, PE/PB/PS, cash flow | Wind/iFind/Tushare/Equal Data | Sina financial three statements, CNINFO announcements + AkShare financials. |
| Announcements | title, date, URL, event type | CNINFO, exchange official sites, Equal Data | SearchHub with official-site preference. |
| Policy/news/research | source, publication date, affected sector/stock, URL | Official sites,券商研报库, Wind/iFind | SearchHub; exclude unsourced self-media as primary evidence. |
| Unlock/reduction risk | unlock date, shares, ratio, holder, reduction plan | Wind/iFind/Tushare/Equal Data | Eastmoney restricted-release/executive-change tables + CNINFO announcements + exchange pages. |

## Code And Market Normalization

- Store canonical codes as `000001.SZ`, `600000.SH`, `688001.SH`, `430047.BJ`.
- Convert to provider formats at adapter boundaries only:
  - TDX/mootdx: strip suffix (`000001`, `600000`); filter `.BJ`.
  - Eastmoney often needs market prefix; encapsulate in provider adapter.
  - Tushare uses `ts_code`.
- Mark stock board: 沪主板、深主板、创业板、科创板、北交所、ST/*ST、停牌、次新、退市整理.
- Do not analyze delisted stocks as investable targets; if present in source lists, label as excluded.

## Freshness Rules

| Data type | Default freshness | Required handling |
| --- | --- | --- |
| Intraday quote / realtime monitoring | current trading session or latest available minute | If outside market hours, state the last update time. |
| Daily market/sector replay | latest A-share trading day | Determine latest trading day first. |
| Fund-flow windows | 3D / 5D / 20D trading-day windows | Use trading days, not calendar days. |
| News/policy for market replay | latest 3 calendar days | Expand only if market holiday makes 3 days too sparse. |
| Sector/stock research events | latest 30 calendar days | Older events may be background, not primary catalyst. |
| Fundamentals | latest disclosed quarter/year | Label disclosure period, not retrieval date. |
| Valuation | latest trading day | State source and field definition. |
| Six-month outlook | current month through +5 months | Use concrete months and observable nodes. |

## Fund-Flow Proxy Rules

Use native `超资入场 3D / 超资抢筹 5D / 超资控盘 20D` only if the source explicitly provides those fields.

If not available, use a disclosed proxy:

```text
3D proxy = sum(main_net_inflow over last 3 trading days) / latest float market cap * 100%
5D proxy = sum(main_net_inflow over last 5 trading days) / latest float market cap * 100%
20D proxy = sum(main_net_inflow over last 20 trading days) / latest float market cap * 100%
```

If main net inflow is missing, large-order net inflow may be a second-level proxy. In HTML, label it clearly:

```text
由于未能直接获取原始“超资”字段，本报告使用“区间主力净流入额 / 最新流通市值”作为超资代理指标。
该指标仅用于资金强度比较，不能完全等同于原始超资数据。
```

## Audit Record

Every report should include a compact data audit section:

| Field | Meaning |
| --- | --- |
| `report_type` | Canonical report id. |
| `target_scope` | Market / sector / stock / watchlist / index / ETF. |
| `trade_date` | Latest trading day used for market data. |
| `retrieved_at` | Local retrieval timestamp with timezone. |
| `providers` | Providers used by category. |
| `source_urls` | Source URLs for news, policy, announcement, or research items. |
| `field_definitions` | Key formula definitions such as fund-flow proxy. |
| `missing_fields` | Missing fields and impact on confidence/ranking. |
| `conflicts` | Conflicting data sources and chosen resolution. |
| `confidence` | High / medium / low with reason. |

## Missing Data Policy

- Use `数据缺失` for unavailable fields. Do not use estimates unless the formula is explicitly defined and marked as proxy.
- If source conflict affects a ranking or recommendation, show both values or disclose the chosen source.
- If a key field is missing for a stock, downgrade its recommendation priority.
- If sector constituents differ across providers, prefer the taxonomy owner or the most mainstream market-data source, and disclose alternatives.
- Do not cite single self-media posts as core evidence for policy, fundamentals, or announcements.

## 2026-07-02 Provider Expansion

This skill now has a concrete provider registry in `references/provider_registry.md` and a runnable probe script:

```bash
python scripts/probe_data_sources.py --samples
```

Newly integrated or documented provider channels:

- XTick: local vendor skill under `xtick/`, with token configuration in `xtick/scripts/Config.py`; preferred Tier-1 source for realtime quote, K-line, index/ETF/HK/convertible bond, hot money, market emotion, indicators, and factors when permission allows.
- Equal Data: configured through `EQUAL_DATA_API_KEY`; preferred for announcements, events, institutional holdings, LHB, insider changes, unlocks, SW industry, index constituents, and news.
- mootdx/TDX: optional realtime/K-line/tick fallback; remember it uses six-digit TDX codes and excludes Beijing Stock Exchange stocks.
- Direct Sina/THS/Eastmoney/CNINFO HTTP: used as low-friction cross-check and public fallback. Add source URL, retrieval time, and field definitions in every report.
- SearchHub expansion: Tavily -> Serper -> SerpAPI -> Brave -> SearxNG. Use official and exchange/regulator sources before self-media when the topic is policy, announcements, fundamentals, or event risk.

Do not commit secrets. `xtick/scripts/Config.py`, `.env`, `__pycache__/`, and `*.pyc` are ignored by Git.

## 2026-07-02 Provider Expansion Round 2

The second expansion focused on page-level data availability. The rule is now: every HTML page must declare its data needs in `references/report_data_matrix.md`, then use provider fallback by field rather than by page.

Newly implemented direct adapters:

- Eastmoney direct HTTP:
  - all-A quote and main-force fund-flow proxy;
  - industry ranking and concept ranking;
  - ETF ranking;
  - board-code search and sector/theme constituents.
  - multi-domain retries plus local JSON cache for `clist` responses, so short source throttles do not immediately blank reports.
- CNINFO:
  - `hisAnnouncement/query` announcement search;
  - stock-code-first event retrieval;
  - sector keyword fallback to top constituent announcements when the sector keyword returns empty.
- THS:
  - industry ranking remains a public fallback;
  - industry detail pages are now used as an Eastmoney-board-constituent fallback when `clist` is throttled or unavailable.
- Sina global:
  - US/HK/global index, HK leaders, USD/CNH and commodity quote snippets;
  - commodity percent change is neutralized unless the Sina payload position is verified for that asset class.
- XTick:
  - market emotion, hot money, realtime news, ETF/index stock master and quant-data probe paths.
- Tushare:
  - generic HTTP client prepared for token-based endpoints without requiring the `tushare` package.

Additional researched sources to keep in the roadmap:

- AkShare skills are useful for A/HK/US/futures/funds/macro and broad no-key fallback.
- Tushare official skills provide a large token-based endpoint catalog and should be used when the user configures `TUSHARE_TOKEN`.
- CNINFO wrapper projects show that full announcement PDF caching and markdown extraction are feasible; add this for single-stock risk and earnings pages.
- Multi-source skills such as `stock-data-skill` and Vibe-Trading emphasize health checks and automatic fallback. Preserve that pattern in `probe_sources`.
- ClawHub A-share daily review skills use Tushare -> AkShare -> search degradation; this skill adopts the same principle but keeps XTick/Eastmoney/CNINFO/Sina as first-class local adapters.

## 2026-07-03 Provider Expansion Round 3

The third expansion closes the biggest no-key data gaps that previously depended on XTick permission, Tushare, or Equal Data:

- Eastmoney datacenter adapters:
  - `RPT_DAILYBILLBOARD_DETAILSNEW` for daily LHB details;
  - `RPT_ORGANIZATION_TRADE_DETAILS` and `RPT_ORGANIZATION_SEATNEW` for institution LHB trades and institution-seat statistics;
  - `RPTA_WEB_MARGIN_DAILYTRADE` for market margin balance and margin trading;
  - `RPT_MUTUAL_DEAL_HISTORY` for Shanghai/Shenzhen/Northbound turnover fallback;
  - `RPT_LIFT_STAGE` for restricted-share unlock calendars;
  - `RPT_EXECUTIVE_HOLD_DETAILS` for executive/insider holding changes;
  - Eastmoney `dataapi/zlsj/list` for fund/QFII/social-security/broker/insurance/trust holdings.
- Sina finance JSON adapter:
  - balance sheet, income statement, and cash-flow statement snapshots through `CompanyFinanceService.getFinanceReport2022`;
  - report item counts are carried into HTML audit so a partial statement can be detected.
- Exchange margin fallback:
  - SSE official `queryMargin.do`;
  - SZSE official `ShowReport/data`, with automatic fallback to the latest published trading day.
- CNINFO reduction verification:
  - reduction announcements are queried around the target stock/sector after structured Eastmoney tables are loaded.

Remaining material gaps:

- ETF share changes/creation-redemption, repo/SHIBOR, pledge/litigation structured fields, revenue mix/business purity, and valuation percentile history still need Tushare/Equal Data/exchange adapters or CNINFO PDF parsing.
- Northbound public fallback currently gives turnover and channel status; true buy/sell/net-buy split is only populated when Eastmoney exposes those fields or a configured professional API is available.
- Industry-chain ontology and global peer-to-A-share mapping need a curated taxonomy, not only live quote data.

## 2026-07-03 Provider Expansion Round 4

This round reviewed 16 user-specified GitHub projects and moved more no-key public channels into the local provider registry. Full review notes live in `references/external_free_sources_review.md`.

Newly implemented no-key adapters:

- Tencent direct quote:
  - `qt.gtimg.cn` realtime quote for A shares, including price, pct change, turnover, PE/PB, market cap, and limit-up/down prices;
  - prefer this for quote fallback on residential networks when Eastmoney disconnects.
- Eastmoney `push2his`:
  - stock daily fund-flow history for recent trading days;
  - 3D/5D/20D fund-flow proxy is now computed as `sum(main_net_inflow) / latest float market cap`;
  - adapter uses retry/cache/lower concurrency because this endpoint can temporarily disconnect under batch load.
- Eastmoney `push2ex`:
  - limit-up pool, break-board pool, limit-down pool, and yesterday-limit performance;
  - covers limit-up emotion, ladder, board quality, and short-term stock-picker pages without requiring XTick/Tushare.
- CNINFO IRM:
  - investor questions and company replies through `irm.cninfo.com.cn`;
  - use this for rumor response, single-stock event risk, and industry-chain diligence.
- DangInvest:
  - market news, industry/sub-industry/concept board summary, and board detail;
  - use this after Eastmoney/THS or as a cross-check for sector heat and constituents.
- hhxg static JSON:
  - daily market snapshot, sentiment, hot themes, limit-up ladder, hot-money summary, sector funds, trading calendar, unlock, earnings, and delivery events;
  - always audit the snapshot date because data may be the latest completed trading day.

Important rule change:

- A field must not stop after only XTick and Eastmoney current quote fail.
- Continue down the ladder: no-key direct HTTP -> optional no-key package wrapper -> configured paid API if available -> official/search confirmation -> explicit `数据缺失`.
- If every historical fund-flow source is blocked, use only the disclosed 1D proxy and downgrade ranking confidence.

Optional package roles, still not hard dependencies:

- AkShare: broad table fallback for fund flow, boards, macro/liquidity, ETF shares, block trades, and CNINFO-derived pages.
- efinance: Eastmoney-backed quote/fund-flow wrapper when direct HTTP formatting changes.
- mootdx/TDX: realtime quote, K-line, tick, F10 fallback; exclude Beijing Stock Exchange.
- Baostock: daily history and basic financial backfill when web providers are unstable.
