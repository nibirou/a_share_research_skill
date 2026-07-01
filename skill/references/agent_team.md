# Multi-Agent Research Team

Use this reference whenever a report requires cross-validation, debate, or a final investment research conclusion.

## Team Roles

| Role | Primary questions | Required evidence | Output |
| --- | --- | --- | --- |
| Data Steward | Is the dataset current, complete, and internally consistent? | Provider logs, trading date, source timestamps, missing fields | Data audit, confidence level, blocked fields. |
| Market Strategist | What is the market regime and style preference? | Index returns, breadth, turnover, policy/news, external markets | Market label, style tilt, event-pricing view. |
| Capital Flow Analyst | Where is money entering/leaving and is it persistent? | Main fund flow, ETF flow, northbound, margin financing, sector breadth | Fund-flow pattern, continuity, crowding warning. |
| Quant Analyst | What do trend, momentum, volatility, breadth, and factor signals say? | MA/returns, volatility, limit-up/down, factor scores, percentiles | Regime score, divergence/resonance signals. |
| Sector Analyst | Which industry/theme logic is real and where in the chain is value captured? | Sector taxonomy, constituents, policy, price/supply data, peers | Sector thesis, chain map, target sector choice. |
| Fundamental Analyst | Which stocks have business purity, earnings support, and valuation logic? | Financials, announcements, revenue mix, margins, PE/PB/PS, ROE | Stock score, valuation diagnosis, business purity. |
| Event Analyst | What has happened recently and what can happen in six months? | Announcements, policy, research, meetings, product launches, unlocks | Catalyst calendar, source-backed event table. |
| Risk Analyst | What can break the thesis? | ST flags, losses, litigation, reductions, unlocks, leverage, source conflicts | Risk matrix, exclusions, downgrade rationale. |
| Bull Researcher | What is the strongest positive case? | Best evidence from all analysts | Bull thesis and required confirmation signals. |
| Bear Researcher | What is the strongest negative case? | Risks, weak evidence, valuation/crowding concerns | Bear thesis and invalidation triggers. |
| Debate Judge | Which argument has better evidence? | Bull/bear record, source quality, missing data | Reconciled verdict and confidence. |
| HTML QA | Does the page meet output constraints and remain readable? | Prompt contract, layout, chart rendering rules, disclaimer | Final checklist, any render warnings. |

## Five-Stage Flow

1. **Analyst Team Collection**  
   Data Steward builds the audit record. Market, capital, quant, sector, fundamental, event, and risk analysts each produce compact findings with sources.

2. **Game Theory And Expectation Gap**  
   Capital Flow Analyst and Market Strategist compare institutional/main-force behavior with public narrative. Label as `抢筹`, `建仓`, `诱多`, `洗盘`, `撤退`, `错杀`, or `等待确认`.

3. **Bull/Bear Debate**  
   Bull Researcher states the strongest investable case. Bear Researcher challenges data quality, valuation, crowding, and event risk. Debate Judge forces both sides to cite evidence and rejects unsupported claims.

4. **Synthesis**  
   Produce a final view with: conclusion, evidence chain, confidence, target watch signals, six-month outlook, and invalidation conditions. For stock-level outputs, use `看好 / 谨慎 / 观望 / 回避`; for watchlist outputs, use `优先关注 / 持续跟踪 / 观望等待 / 暂不关注`.

5. **Risk Control And HTML QA**  
   Risk Analyst removes ST/*ST or delisting-risk names from recommendations, downgrades missing-data names, and verifies that the HTML includes source/audit notes and investment disclaimer.

## Role Output Contract

Each role should return compact structured findings before the final HTML is rendered:

```json
{
  "role": "资金流分析师",
  "verdict": "资金从高拥挤科技链转向低位政策催化链",
  "confidence": "medium",
  "evidence": [
    {"claim": "3D主力净流入强于5D", "source": "provider", "date": "YYYY-MM-DD"},
    {"claim": "ETF净申购扩大", "source": "provider", "date": "YYYY-MM-DD"}
  ],
  "risks": ["资金持续性不足", "数据仅为代理口径"],
  "needed_checks": ["下个交易日成交额能否放大"]
}
```

## Debate Rules

- One analyst may not use another analyst's conclusion as evidence; use raw source facts or formulas.
- The Bear Researcher must challenge at least one data quality issue and one thesis issue.
- The Debate Judge must explicitly explain why the final conclusion chooses one side or keeps a lower-confidence view.
- If the recommendation depends on a missing field, mark it as observation only.
- Do not convert a trading signal into a guaranteed profit claim.

## Scoring Guidance

Use scores to rank, not to imply precision. Keep formulas visible in the report.

### Sector Composite Score

| Factor | Weight |
| --- | ---: |
| 3D fund strength | 20 |
| 5D fund strength | 15 |
| 20D fund strength | 20 |
| Positive fund-flow breadth | 10 |
| Three-window all-positive breadth | 10 |
| Price/fund-flow match | 5 |
| Cross-theme heat | 10 |
| Fundamental cycle support | 5 |
| Policy/industry catalyst | 5 |

### Stock Quality Score

| Factor | Points |
| --- | ---: |
| Three fund windows positive | +30 |
| 20D fund strength top 5 within target sector | +20 |
| Acceleration pattern: 3D > 5D > 20D | +15 |
| Float cap matches fund volume | +15 |
| Stable flow window: standard deviation below 50% of average | +20 |
| ST/*ST | -40 |
| Recent annual loss without clear improvement | -20 |
| Recent reduction announcement | -15 |
| Six-month major unlock pressure | -10 |
| Severe missing fundamentals | -10 |
| Single-source proxy fund-flow data | -5 |
| Unverified theme relation | -10 |

## Recommendation Language

Allowed stock-level judgments:

- `看好`: evidence supports funds + fundamentals + catalyst, and risks are controlled.
- `谨慎`: upside exists but valuation, crowding, or data quality limits confidence.
- `观望`: logic is plausible but needs a concrete confirmation signal.
- `回避`: funds, fundamentals, or risk screen is unfavorable.

Allowed watchlist priority:

- `优先关注`: score >= 80 and a concrete entry trigger exists.
- `持续跟踪`: score 65-79; wait for confirmation or better price.
- `观望等待`: score 50-64; thesis incomplete or timing poor.
- `暂不关注`: score < 50 or hard risk.

Always include invalidation triggers such as: break below key MA, announcement contradiction, missing order/price data, policy delay, earnings miss, or fund-flow reversal.
