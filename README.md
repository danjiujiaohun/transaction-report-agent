# 股票市场公司分析报告 Agent

一个基于 **FastAPI + LangGraph** 的 A 股上市公司分析报告生成服务：接收公司名称，自动规划检索点、采集 A 股结构化数据 + 联网搜索，最终按既定 skill 规则生成 Markdown 分析报告。前端可通过 REST API 获取报告数据。

## 特性

- **三段式流水线**：`plan → search → report`（LangGraph 编排）
- **A 股结构化取数**：实时行情、财务三表、估值历史、研报、一致预期 EPS、股东户数、分红送转、资金流、龙虎榜
- **联网搜索**：可移植的 Tavily 接口（备选 AutoGLM WebSearch）
- **可插拔 LLM**：任意 OpenAI 兼容接口（DeepSeek / Qwen / OpenAI）或本地 Ollama
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
│       └── a_stock/          # A 股取数工具（行情/财务/估值/研报/资金面/信号）
├── skills/                   # 报告生成规则（Markdown，见下方「致谢」）
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

> **联网搜索二选一**：填了 `TAVILY_API_KEY` 即走 Tavily（推荐，部署到新环境只需配这一个 key）；都不填且本地有 53699 token 服务时才走 AutoGLM，否则搜索自动降级为「结构化数据 + 搜索暂缺」。

## 安装与启动

```bash
# 1. 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量（见上一节）
cp .env.example .env   # 然后编辑 .env 填入 LLM 与搜索 Key

# 4. 启动服务（两种方式任选）
# 方式一：直接使用虚拟环境内的 uvicorn，无需激活
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# 方式二：激活虚拟环境后启动（激活仅对当前终端生效，新开终端需重新 source）
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动后可访问：

- 健康检查：`GET http://localhost:8000/api/health`
- Swagger 文档：`http://localhost:8000/docs`

### API 用法

分析采用**异步任务**模式：提交后立即返回 `task_id`，前端轮询任务状态直到 `done` 再取报告（单次完整生成约 1~3 分钟）。

**1. 提交分析任务**（立即返回，`202 Accepted`）：

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"company": "贵州茅台"}'
```

响应：

```json
{
  "task_id": "c3c561e018ba",
  "company": "贵州茅台",
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
  "skills_loaded": 11,
  "search_available": true
}
```

## 报告生成规则（skills）

`skills/` 目录存放报告生成规则，为 Markdown 形式的规则说明（含数据源、字段口径、防封限流约定），在每次分析时注入到 LLM prompt 中，约束报告结构、数据口径与「不得臆造数据」的底线。

> **致谢**：本项目的报告生成 skills 出自仓库 <https://github.com/zengfancy/invest-skill>，在此对其作者表示感谢。

## 常见问题

- **搜索结果为空 / `search_available: false`**：检查 `TAVILY_API_KEY` 是否配置、网络是否可达 `https://api.tavily.com`。
- **A 股数据取不到**：多为海外网络或公司内网无法直连国内接口；`资金流`（东财 push2his）对部分 IP 有连接级风控，会优雅降级为「获取失败」而非报错。
- **本地 502（开启代理时）**：本项目已自动把 `127.0.0.1`/`localhost` 加入 `NO_PROXY`，避免 Ollama 等本地服务被系统代理拦截。