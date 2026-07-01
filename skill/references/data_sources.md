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
| Fund flow | main net inflow, large-order flow, northbound, ETF flow | Wind/iFind/XTick/Equal Data | Eastmoney/同花顺/AkShare; mark as proxy if needed. |
| Fundamentals | revenue, net profit, margins, ROE, PE/PB/PS, cash flow | Wind/iFind/Tushare/Equal Data | CNINFO announcements + AkShare financials. |
| Announcements | title, date, URL, event type | CNINFO, exchange official sites, Equal Data | SearchHub with official-site preference. |
| Policy/news/research | source, publication date, affected sector/stock, URL | Official sites,券商研报库, Wind/iFind | SearchHub; exclude unsourced self-media as primary evidence. |
| Unlock/reduction risk | unlock date, shares, ratio, holder, reduction plan | Wind/iFind/Tushare/Equal Data | Exchange/CNINFO announcements. |

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
