# A-Share Research HTML Skill

一个可运行的 A 股综合投研 Skill 工程骨架：行情数据获取、联网事件搜索、多智能体分析、HTML 页面生成、FastAPI 后端和 Vue 前端页面中心。

## 快速启动

```bash
cd a_share_research_skill
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_once.py --all
uvicorn backend.app.main:app --host 0.0.0.0 --port 8787 --reload
```

打开 `http://127.0.0.1:8787`。

## Skill 资料结构

- `skill/SKILL.md`：轻量入口与报告路由。
- `skill/references/data_sources.md`：行情、资金、财务、公告、新闻数据源分层与审计规则。
- `skill/references/agent_team.md`：多智能体投研角色、辩论流程与评分规则。
- `skill/references/html_prompt_library.md`：现有功能优化版提示词与新增 HTML 报告提示词。
- `docs/Prompt/FunctionPrompt.ipynb`：由提示词库同步生成的 notebook 版本。

## 当前可运行报告类型

- `market_replay`：行情多维度复盘 HTML
- `quant_factor`：大盘量化因子 HTML
- `sector_stock`：板块个股逐一分析 HTML
- `agent_debate`：多智能体投研 HTML

## 已设计扩展报告类型

提示词库已补充：板块资金轮动、聪明资金攻击面、板块估值诊股、趋势共振、自选股终端、指数/ETF 监控、流动性仪表盘、财报催化日历、单股事件风险、产业链图谱、海外映射等功能。当前后端仍需继续扩展 `Pipeline` 才能一键运行这些新类型。

## 可选环境变量

- `DATA_PROVIDER=demo|akshare`
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`
- `TAVILY_API_KEY` / `SERPER_API_KEY` / `SEARXNG_URL`
- `TUSHARE_TOKEN` / `XTICK_TOKEN`

## 安全说明

本项目仅用于研究和页面生成，不自动下单，不承诺收益。第三方 Skill/ClawHub 仓库只建议做架构参考；生产环境必须做代码审计、版本锁定、哈希校验和沙箱隔离。
