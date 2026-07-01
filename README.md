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

## 报告类型

- `market_replay`：行情多维度复盘 HTML
- `quant_factor`：大盘量化因子 HTML
- `sector_stock`：板块个股逐一分析 HTML
- `agent_debate`：多智能体投研 HTML

## 可选环境变量

- `DATA_PROVIDER=demo|akshare`
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`
- `TAVILY_API_KEY` / `SERPER_API_KEY` / `SEARXNG_URL`
- `TUSHARE_TOKEN` / `XTICK_TOKEN`

## 安全说明

本项目仅用于研究和页面生成，不自动下单，不承诺收益。第三方 Skill/ClawHub 仓库只建议做架构参考；生产环境必须做代码审计、版本锁定、哈希校验和沙箱隔离。
