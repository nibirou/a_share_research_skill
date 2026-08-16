# HTML Prompt Library Index

This file is only a router. For full prompt text, read the corresponding standalone Markdown file under:

`references/html_prompts/`

Each file is a complete, standalone HTML report prompt with AI-autonomous data retrieval, data audit rules, multi-agent verification, missing-data handling, HTML layout constraints, risk disclosure, and final self-checks.

## Prompt File Map

| Report id | Prompt file |
| --- | --- |
| `market_replay` | `references/html_prompts/01_market_replay.md` |
| `quant_factor` | `references/html_prompts/02_quant_factor.md` |
| `sector_stock` | `references/html_prompts/03_sector_stock_full_market.md` |
| `sector_flow_rotation` | `references/html_prompts/04_sector_flow_rotation.md` |
| `smart_money_clusters` | `references/html_prompts/05_smart_money_attack_width.md` |
| `sector_valuation_diagnosis` | `references/html_prompts/06_sector_valuation_diagnosis.md` |
| `trend_resonance` | `references/html_prompts/07_trend_resonance.md` |
| `watchlist_terminal` | `references/html_prompts/08_watchlist_terminal.md` |
| `index_etf_monitor` | `references/html_prompts/09_index_etf_style_monitor.md` |
| `liquidity_dashboard` | `references/html_prompts/10_liquidity_dashboard.md` |
| `earnings_catalyst_calendar` | `references/html_prompts/11_earnings_catalyst_calendar.md` |
| `single_stock_event_risk` | `references/html_prompts/12_single_stock_event_risk.md` |
| `industry_chain_map` | `references/html_prompts/13_industry_chain_map.md` |
| `global_mapping` | `references/html_prompts/14_global_mapping.md` |
| `agent_debate` | `references/html_prompts/15_agent_debate_report.md` |

## Use Guidance

1. Identify the report id from the user request.
2. Read only the matching prompt file to avoid loading unrelated long prompts.
3. Also read `skill/references/data_sources.md` and `skill/references/report_data_matrix.md` when the task needs current data.
4. Also read `skill/references/agent_team.md` when the task asks for multi-agent research, debate, or risk review.
5. Preserve the chosen prompt's HTML module order and output constraints unless the user explicitly asks to modify them.
