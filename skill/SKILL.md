---
name: a-share-research-html
description: 当用户需要生成 A 股行情复盘、量化因子、板块个股、多智能体投研 HTML 页面时使用。本 Skill 获取行情/资金/政策/新闻数据，调用多智能体交叉验证，输出完整 HTML 页面并同步到页面中心。
---

# A 股综合投研 HTML Skill

## 触发场景

- “生成今日 A 股行情复盘 HTML”
- “刷新大盘量化因子页面”
- “分析光伏设备板块个股并推荐标的”
- “用多智能体团队做 A 股投研报告”
- “刷新所有投研 HTML 页面”

## 固定工作流

1. 识别任务类型：`market_replay` / `quant_factor` / `sector_stock` / `agent_debate`。
2. DataHub 获取行情、指数、板块、资金、因子、个股和公告数据。
3. SearchHub 联网搜索近 3 天或近 30 天事件。
4. AgentTeam 由宏观、资金、量化、行业、风险智能体交叉分析。
5. HtmlRenderer 输出完整 HTML，使用 Chart.js 4.4.0 CDN。
6. 保存到 `backend/app/static/reports/` 并返回链接。

## 命令

```bash
python scripts/generate_once.py --all
python scripts/generate_once.py --report market_replay
python scripts/generate_once.py --report quant_factor
python scripts/generate_once.py --report sector_stock --sector 光伏设备
uvicorn backend.app.main:app --host 0.0.0.0 --port 8787
```

## 输出硬约束

- 输出完整 HTML 文件，不输出 Markdown。
- 深色主题：`#0d1117` / `#161b22` / `#30363d`。
- A 股配色：涨/流入红 `#f85149`，跌/流出绿 `#3fb950`。
- 必须引入 `https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js`。
- 必须包含“不构成投资建议”的免责声明。
