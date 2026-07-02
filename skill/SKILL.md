---
name: a-share-research-html
description: Use when Codex needs A-share market data retrieval, A股行情复盘, 量化因子, 板块个股分析, 多智能体投研, or HTML report generation/refresh. Supports market replay, quant factors, sector/stock selection, fund rotation, smart-money clusters, sector valuation, trend resonance, watchlists, index/ETF monitoring, liquidity dashboards, earnings/event calendars, single-stock event risk, and industry-chain analysis.
---

# A-Share Research HTML Skill

## Core Workflow

1. Identify the requested report type and target scope: market, index/ETF, sector/theme, stock, watchlist, event calendar, liquidity, or multi-agent debate.
2. Load only the needed references:
   - Provider routing, source priority, integration notes, and environment variables: `references/provider_registry.md`.
   - Data freshness, code normalization, audit rules, and missing-data policy: `references/data_sources.md`.
   - Multi-agent roles, debate flow, and verification contracts: `references/agent_team.md`.
   - HTML prompt templates for each report type: `references/html_prompt_library.md`.
3. Fetch or verify current data before analysis. For market data, use the latest A-share trading day or current trading session. For policy/news/events, default to 3 days for market replay and 30 days for sector/stock research unless the user requests another window.
4. Mark every material data point with provider, data date, retrieval time, and method. If a field cannot be verified, write `数据缺失`; do not infer or fabricate values.
5. Prefer configured professional providers first, then open/public fallback providers:
   - XTick / Tushare / Equal Data when configured.
   - AkShare / mootdx / efinance when installed.
   - Sina / Eastmoney / THS / CNINFO / exchange pages as direct HTTP or web fallback.
   - Tavily / Serper / SerpAPI / Brave / SearxNG for news and policy search.
6. Run the relevant analyst roles, reconcile conflicting conclusions, and preserve dissenting risk views.
7. Render a complete responsive HTML report and save it under `backend/app/static/reports/` when running in this repository.

## Report Routing

Use these canonical report ids when possible:

| Report id | Use for |
| --- | --- |
| `market_replay` | Daily or intraday A-share market replay, index breadth, sector rotation, event pricing. |
| `quant_factor` | Index timing, momentum/emotion/capital/composite factors, regime signals. |
| `sector_stock` | Full-market sector/theme scan, target sector selection, constituent-by-constituent analysis. |
| `sector_flow_rotation` | Cross-sector fund inflow/outflow and six-month rotation outlook. |
| `smart_money_clusters` | Smart-money stock clusters and sector attack-width diagnostics. |
| `sector_valuation_diagnosis` | Sector constituents valuation, business purity, fundamentals, catalysts, and ranking. |
| `trend_resonance` | Sector-stock trend strength resonance, divergence, and selected stock pool. |
| `watchlist_terminal` | User watchlist terminal; user may provide only stock codes/names and the skill fetches the rest. |
| `index_etf_monitor` | Broad/narrow index and ETF style monitoring. |
| `liquidity_dashboard` | Northbound, margin financing, ETF flow, turnover, repo/FX liquidity dashboard. |
| `earnings_catalyst_calendar` | Earnings preview, disclosure windows, event and policy catalyst calendar. |
| `single_stock_event_risk` | Single-stock event, announcement, sentiment, funds, valuation, and risk radar. |
| `industry_chain_map` | Sector industry-chain map, upstream/downstream transmission, and A-share beneficiary matrix. |
| `global_mapping` | HK/US/global peer mapping into A-share themes and risk transfer. |

Current runnable backend code supports `market_replay`, `quant_factor`, `sector_stock`, and `agent_debate`. Additional report prompts are available in the prompt library and can be wired into `Pipeline` incrementally.

## HTML Constraints

- Output a complete HTML file, not Markdown or JSON, unless the user explicitly asks for prompt text.
- Use the A-share color convention: rise/inflow/bullish red `#f85149`; fall/outflow/bearish green `#3fb950`.
- Use dark terminal styling with background `#0d1117`, cards `#161b22`, borders `#30363d`.
- Include Chart.js `https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js` for Chart.js reports. Use ECharts only for templates that explicitly require terminal-style watchlist graphs.
- Keep paragraphs short; prefer cards, tables, timelines, labels, and charts.
- Include a visible disclaimer: `基于 AI 分析 + 联网公开信息，仅供研究参考，不构成投资建议。投资有风险，入市需谨慎。`
- Include a data audit section with provider, retrieval time, data date, missing fields, conflicts, and confidence.

## Commands

```bash
python scripts/probe_data_sources.py --samples
python scripts/generate_market_replay_live.py
python scripts/generate_once.py --all
python scripts/generate_once.py --report market_replay
python scripts/generate_once.py --report quant_factor
python scripts/generate_once.py --report sector_stock --sector 光伏设备
uvicorn backend.app.main:app --host 0.0.0.0 --port 8787
```
