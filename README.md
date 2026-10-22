# 股票市场公司分析报告 Agent

一个基于 **FastAPI + LangGraph** 的上市公司分析报告生成服务：接收公司名称或股票代码，自动规划检索点、采集 A 股/美股结构化数据 + 联网搜索，最终按既定 skill 规则生成**全英文** Markdown 分析报告。项目内置网页前端，浏览器打开即可输入股票查看报告，同时提供 REST API 供二次集成。

## 特性

- **三段式流水线**：`plan → search → report`（LangGraph 编排）
- **A 股结构化取数**：实时行情、财务三表、估值历史、研报、一致预期 EPS、股东户数、分红送转、资金流、龙虎榜
- **美股结构化取数**：行情/估值快照（含分析师目标价）、年报三表关键行、近一年 K 线摘要（yfinance，Yahoo/SEC 数据源）
- **全英文报告（强制）**：报告生成后自动扫描中文字符，检出即触发一次英文重写修复
- **联网搜索**：可移植的 Tavily 接口（备选 AutoGLM WebSearch）
- **可插拔 LLM**：任意 OpenAI 兼容接口（DeepSeek / Qwen / OpenAI）或本地 Ollama
- **内置网页前端**：黑底科技感页面，访问 `/` 即可输入股票名称/代码生成并在线查看报告
- **REST API + CORS**：前端可直接跨域调用

## 目录结构

```
transaction-report-agent/
├── app/
│   ├── main.py               # FastAPI 入口与路由
│   ├── config.py             # 配置（.env 加载）
│   ├── llm.py                # LLM 工厂（OpenAI 兼容 / Ollama）
│   ├── agent/                # LangGraph：state / nodes / graph
│   ├── models/schemas.py     # 请求/响应模型
│   ├── skills/loader.py      # 加载 skills/*.md 规则并注入 prompt
│   └── tools/
│       ├── web_search.py     # 联网搜索（Tavily / AutoGLM）
│       ├── a_stock/          # A 股取数工具（行情/财务/估值/研报/资金面/信号）
│       └── us_stock/         # 美股取数工具（ticker 归一化/限流/代理、yfinance 采集）
├── skills/                   # 报告生成规则（Markdown，见下方「致谢」）
├── static/                   # 网页前端（黑底科技感 UI，调用后端 REST API）
├── requirements.txt
├── .env.example
└── README.md
```

## 环境要求

- Python 3.10+（本项目在 3.13 验证）
- 国内网络（A 股数据源为腾讯/新浪/东财/baostock 国内接口，海外网络可能受限）

## 配置方法

1. 复制环境变量模板：

```bash
cp .env.example .env
```

2. 编辑 `.env`，按需填写以下配置：

| 变量 | 必填 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | 是 | `openai`（推荐）或 `ollama` |
| `OPENAI_BASE_URL` | 当 provider=openai | OpenAI 兼容接口地址，如 `https://api.deepseek.com` |
| `OPENAI_API_KEY` | 当 provider=openai | 你的 API Key |
| `OPENAI_MODEL` | 当 provider=openai | 模型名，如 `deepseek-chat` |
| `OLLAMA_BASE_URL` | 当 provider=ollama | 本地 Ollama 地址，默认 `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | 当 provider=ollama | 本地模型名，默认 `qwen3.5:9b` |
| `TAVILY_API_KEY` | 推荐 | Tavily 联网搜索 Key（跨环境可移植，主用） |
| `WEBSEARCH_TOKEN_URL` | 否 | AutoGLM 搜索 token 服务地址（无 Tavily key 时的备选） |
| `SKILLS_DIR` | 否 | skills 目录，默认 `skills` |
| `HOST` / `PORT` | 否 | 服务监听地址/端口，默认 `0.0.0.0:8000` |
| `US_STOCK_PROXY` | 否 | 美股取数 HTTP 代理（如 `http://127.0.0.1:7890`）；Yahoo/SEC 在部分网络直连会被 403/限流，仅美股流量走此代理，A 股源不受影响。留空直连 |

> **联网搜索二选一**：填了 `TAVILY_API_KEY` 即走 Tavily（推荐，部署到新环境只需配这一个 key）；都不填且本地有 53699 token 服务时才走 AutoGLM，否则搜索自动降级为「结构化数据 + 搜索暂缺」。

## 安装与启动

在目标服务器上执行以下步骤即可完成部署：

```bash
# 1. 拉取代码并进入项目目录
git clone <your-repo-url> transaction-report-agent
cd transaction-report-agent

# 2. 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量（见上一节）
cp .env.example .env   # 然后编辑 .env 填入 LLM 与搜索 Key

# 5. 启动服务（两种方式任选）
# 方式一：直接使用虚拟环境内的 uvicorn，无需激活
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# 方式二：激活虚拟环境后启动（激活仅对当前终端生效，新开终端需重新 source）
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> 服务监听 `0.0.0.0:8000`，同一台服务器或局域网内可直接用浏览器访问；若部署在云端，需在安全组/防火墙放行 `8000` 端口。

启动后可访问：

- **网页前端**：`http://<服务器地址>:8000/`（输入股票名称/代码即生成报告）
- 健康检查：`http://localhost:8000/api/health`
- Swagger 文档：`http://localhost:8000/docs`

### 网页前端

前端页面由后端同一进程托管（`static/` 目录），**无需单独构建或另起 Node 服务**，部署到新服务器后直接打开浏览器即可使用：

1. 打开 `http://<服务器地址>:8000/`。
2. 在输入框输入公司名称或股票代码：美股如 `AAPL`、`MSFT`、`TSLA`（首页 TRY 快捷按钮即为美股市值 Top 10），A 股如 `贵州茅台`、`600519`。
3. 点击「生成报告」（或按回车），页面显示四段式进度（规划 → 采集 → 生成 → 完成）。
4. 完成后自动渲染报告：左侧目录导航、Markdown 排版（表格/代码块）、复制原文、导出 PDF。

页面数据完全来自后端 `/api/*` 接口（健康检查 / 提交任务 / 轮询状态），因此只需启动后端一个进程，即可同时提供页面与接口。

### API 用法

分析采用**异步任务**模式：提交后立即返回 `task_id`，前端轮询任务状态直到 `done` 再取报告（单次完整生成约 1~3 分钟）。

**1. 提交分析任务**（立即返回，`202 Accepted`）：

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"company": "AAPL"}'
```

响应：

```json
{
  "task_id": "c3c561e018ba",
  "company": "AAPL",
  "status": "running",
  "phase": "规划检索关键词",
  "report": null,
  "error": null
}
```

**2. 轮询任务状态**：

```bash
curl http://localhost:8000/api/analyze/c3c561e018ba
```

状态字段说明：

- `status`：`pending`（排队）→ `running`（生成中）→ `done`（完成）/ `failed`（失败）
- `phase`：当前阶段文案，如 `规划检索关键词` / `采集结构化数据与联网搜索` / `生成分析报告` / `完成`
- `report`：仅 `status=done` 时有 Markdown 报告全文
- `error`：仅 `status=failed` 时有错误信息

> 任务存储于进程内存，服务重启后任务即清空；多实例部署时可将 [app/agent/tasks.py](app/agent/tasks.py) 替换为 Redis/DB 实现。

健康检查响应（含搜索可用性）：

```json
{
  "status": "ok",
  "llm_provider": "openai",
  "llm_model": "deepseek-chat",
  "skills_loaded": 19,
  "search_available": true
}
```

## 报告生成规则（skills）

`skills/` 目录存放报告生成规则，为 Markdown 形式的规则说明（含数据源、字段口径、防封限流约定），在每次分析时注入到 LLM prompt 中，约束报告结构、数据口径与「不得臆造数据」的底线。

> **致谢**：本项目的报告生成 skills 出自仓库 <https://github.com/zengfancy/invest-skill>，在此对其作者表示感谢。

## 常见问题

- **首页 `/` 返回 404**：确认项目根目录存在 `static/` 目录（内置网页前端）；若从旧版本升级，重启服务即可加载静态挂载。
- **搜索结果为空 / `search_available: false`**：检查 `TAVILY_API_KEY` 是否配置、网络是否可达 `https://api.tavily.com`。
- **A 股数据取不到**：多为海外网络或公司内网无法直连国内接口；`资金流`（东财 push2his）对部分 IP 有连接级风控，会优雅降级为「获取失败」而非报错。
- **美股结构化数据取不到（quote/financials/history 显示获取失败）**：多为 Yahoo 对当前出口 IP 直连 403/限流；配置 `US_STOCK_PROXY` 走可用代理后重试。代理不可用时报告仍会生成，只是降级为纯联网搜索并在报告中标注数据缺口。
- **本地 502（开启代理时）**：本项目已自动把 `127.0.0.1`/`localhost` 加入 `NO_PROXY`，避免 Ollama 等本地服务被系统代理拦截。