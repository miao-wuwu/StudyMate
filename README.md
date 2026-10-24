# StudyMate — 全栈学习管理平台

StudyMate 是一个面向个人学习场景的全栈学习管理平台，帮助用户管理学习笔记、规划学习任务、记录每日打卡，并通过专注计时与学习统计追踪学习进度。

项目采用 **React + TypeScript** 构建前端，使用 **Python + FastAPI** 构建后端，并通过 **SQLite + SQLAlchemy** 实现学习数据的持久化存储。

本项目主要用于实践前后端分离开发、REST API 设计、数据库操作、自动化测试和持续集成。

## 项目预览

### 学习统计仪表盘

![StudyMate 学习统计仪表盘](screenshots/dashboard.png)

StudyMate 提供学习笔记、任务管理、每日打卡、专注计时和学习统计等功能，帮助用户记录学习过程并追踪学习进度。

## 项目功能

### 1. 学习笔记管理
- 新增、查看、编辑和删除学习笔记
- 支持笔记搜索和分类管理
- 使用 SQLite 持久化保存笔记数据

### 2. 学习任务管理
- 创建和管理个人学习任务
- 切换任务完成状态
- 支持任务查询与筛选

### 3. 每日学习打卡
- 记录每日学习情况
- 通过打卡日历查看学习记录
- 统计累计打卡与连续打卡情况

### 4. 专注计时
- 使用计时功能辅助专注学习
- 记录学习时段，为学习统计提供数据

### 5. 学习统计仪表盘
- 汇总学习相关数据
- 展示学习进度与统计信息

### 6. 成就徽章
- 展示学习过程中的阶段性成果

> 说明：具体功能、统计口径和成就解锁规则以当前代码实现为准。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端框架 | React |
| 开发语言 | TypeScript、Python |
| 前端构建工具 | Vite |
| 页面样式 | CSS |
| 后端框架 | FastAPI |
| 数据库 ORM | SQLAlchemy |
| 数据库 | SQLite |
| 自动化测试 | pytest、FastAPI TestClient |
| 持续集成 | GitHub Actions |
| 版本控制 | Git |
| 代码托管 | GitHub |

## 项目结构

```text
StudyMate/
├── main.py
├── tests/
│   ├── test_notes.py
│   └── test_tasks.py
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
├── screenshots/
│   └── dashboard.png
├── .github/
│   └── workflows/
│       └── tests.yml
├── README.md
└── studymate.db
```

> `studymate.db` 为本地运行时使用的 SQLite 数据库文件。数据库文件、Python 虚拟环境、`node_modules` 和构建产物不应作为普通源代码提交。

## 环境要求

开始运行项目前，请准备：

- Python 3.13（或经项目验证兼容的版本）
- Node.js 和 npm
- Git

## 本地运行

前端和后端需要分别启动，并保持各自的终端运行。

### 1. 获取项目代码

```powershell
git clone https://github.com/miao-wuwu/StudyMate.git
cd StudyMate
```

如果仓库是私有的，需要先获得访问权限。

### 2. 安装并启动后端

在项目根目录 `StudyMate` 中打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install fastapi "uvicorn[standard]" sqlalchemy pytest httpx
python -m uvicorn main:app --reload
```

后端启动后，可访问：

- 后端地址：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs

### 3. 安装并启动前端

另开一个终端，进入前端目录：

```powershell
cd frontend
npm install
npm run dev
```

根据终端输出打开 Vite 提供的本地开发地址，通常为：

http://localhost:5173/

### 4. 检查前端生产构建

在 `frontend` 目录执行：

```powershell
npm run build
```

如果构建成功，说明前端代码通过了当前构建流程的检查。

## 自动化测试

项目使用 pytest 和 FastAPI TestClient 对后端 API 进行自动化测试。

目前已编写的测试包括：

- 笔记 API：创建、查询、搜索、编辑和删除，以及不存在的笔记处理
- 任务 API：创建、查询、切换完成状态、删除和空白标题校验

运行全部测试：

```powershell
python -m pytest tests -v
```

测试使用独立的临时数据库，避免测试数据污染日常使用的学习记录。

项目通过 GitHub Actions 自动执行测试工作流，帮助发现代码修改引入的问题。

## 数据存储

项目使用 SQLite 保存学习数据，并通过 SQLAlchemy 操作数据库。

本地数据库文件通常位于项目根目录下的 `studymate.db`。首次运行时，后端会根据数据库初始化逻辑创建所需的数据表。

数据库表结构和初始化行为以当前后端模型代码为准。

## 当前开发状态

目前已实现或已验证的内容包括：

- 前后端分离架构
- React + TypeScript 前端
- FastAPI 后端及 API 文档
- 学习笔记的新增、查询、编辑、删除与搜索
- SQLite 数据持久化
- 学习任务管理
- 每日学习打卡
- 学习统计仪表盘
- 专注计时与成就界面
- 笔记和任务 API 自动化测试
- Git 版本管理与 GitHub Actions 持续集成

## AI 学习助手（本地大模型）

学习笔记、计划、打卡之外，StudyMate 还带了一个**完全跑在本机**的 AI 模块：不联网、不花钱、不上传任何数据。

### 组成

- **推理**：Ollama + Qwen2.5-3B-Instruct（GGUF Q4_K_M，约 2.1 GB），通过 `ollama create` 从本地 GGUF 导入为 `studymate-qwen`
- **向量**：Ollama `nomic-embed-text`（274 MB），把文本块映射成 768 维向量
- **检索**：numpy 暴力余弦相似度（向量以 float32 BLOB 存在同一个 `studymate.db` 里，新增 `documents` / `chunks` 两张表，不用额外向量库）
- **解析**：PyMuPDF 抽取 PDF 文本，按「段 → 句」贪心分块（500 字 / 重叠 80 字）

### 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/ai/health` | 探活，返回模型名、向量模型、资料库统计 |
| POST | `/ai/chat` | 多轮对话（`messages: [{role, content}]`） |
| POST | `/ai/ask` | 基于资料库提问，返回 `answer` + `sources`（含相似度） |
| GET | `/ai/documents` | 资料列表 |
| POST | `/ai/documents` | 直接提交纯文本入库 |
| POST | `/ai/documents/upload` | 上传 `.txt/.md/.pdf` 文件入库 |
| DELETE | `/ai/documents/{id}` | 删除资料（连带删除其文本块） |
| POST | `/ai/search` | 只做检索，返回命中的文本块 |
| POST | `/ai/summary` | 总结资料：返回 `summary` + `points`（要点列表），可指定 `document_id` 或整库 |
| POST | `/ai/quiz` | 按资料出选择题：返回题干、四个选项、正确答案与解析，`count` 默认 3 |

资料库为空时，`/ai/ask` 会自动退化为普通对话（返回 `mode: "chat"`）；有资料时返回 `mode: "rag"` 并在答案里标注 `[1] [2]` 来源。

### 启动

```powershell
# 1. 启动 Ollama（安装后一般开机自启）
ollama serve

# 2. 准备模型
ollama create studymate-qwen -f _downloads\Modelfile.qwen25-3b
ollama pull nomic-embed-text

# 3. 启动后端与前端
uvicorn main:app --reload
cd frontend; npm install; npm run dev
```

前端打开后切到「AI 助手」标签：左边对话（可勾选「结合资料回答」），右边上传资料、查看与删除。

对话区上方还有两个按钮：

- **总结资料**：对整库（或指定文档）生成一段摘要和 5 条要点
- **出 3 道题**：按资料出选择题，点选项立刻判对错并显示解析

### 关于出题质量

本地跑的是 3B 的小模型，出题能力有限：偶尔会出现「多个选项都说得通」或者题目之间问得太像的情况。代码里已经做了三层兜底——prompt 明确要求每题考不同知识点、禁止「下列描述正确的是」这类只有语序差异的选项；解析阶段丢弃答案不在 A/B/C/D 或无选项的题目；再按题干和选项集去重。如果对题目质量要求高，把 `OLLAMA_MODEL` 换成 7B（`qwen2.5:7b-instruct-q4_k_m`，约 4.7 GB，8 GB 显存可单独跑）会明显更稳。

### 可配置项

复制 `.env.example` 为 `.env` 后按需修改，默认值即可在本机零成本运行：

- `LLM_PROVIDER`：`ollama`（默认）或 `deepseek`
- `OLLAMA_MODEL` / `OLLAMA_EMBED_MODEL` / `OLLAMA_HOST`
- `NUM_CTX`、`KEEP_ALIVE`（空闲多久卸载模型，默认 5m）、`TEMPERATURE`
- `CHUNK_SIZE`、`CHUNK_OVERLAP`、`TOP_K`
- `LLM_HISTORY_MAX_CHARS`（默认 6000）、`LLM_HISTORY_MAX_MESSAGES`（默认 20）：多轮对话的历史预算，超出后从最早的对话开始丢弃，并在 system 提示里加一句「更早的对话已省略」，避免长对话把 `num_ctx` 撑爆
- 切到 `deepseek` 时需要 `DEEPSEEK_API_KEY`（放 `.env`，已在 `.gitignore` 中忽略）

### 显存与性能参考

RTX 4060 Laptop（8 GB）实测：Qwen2.5-3B Q4 占显存约 2.4 GB，生成速度约 12 tokens/s，首次加载约 30 秒；`keep_alive` 到期后自动卸载，不常驻占卡。显存不足时 Ollama 会自动把部分层放到 CPU（`ollama ps` 可见），只是变慢，不会崩。

### 演示流程（3 分钟）

1. **准备**：`ollama serve` → `uvicorn main:app --reload` → `cd frontend && npm run dev`，浏览器打开 `http://localhost:5173/?page=ai`
2. **看状态**：右上角徽标显示「已连接本地模型 · studymate-qwen · 向量 nomic-embed-text」，说明后端与模型都通了
3. **上传资料**：把一份课程 PDF 或 Markdown 拖到右侧「上传 PDF / Markdown / TXT」，列表里出现标题、字数和分块数
4. **带出处提问**：勾选「结合资料回答」，问一个资料里才有答案的问题，回答下方会列出 `[1] 《标题》第 n 段 · 相似度 0.xx`
5. **总结要点**：点「总结资料」，得到一段摘要 + 要点列表
6. **出题自测**：点「出 3 道题」，逐题点选项，选对变绿、选错标红并给出解析
7. **对照实验**：取消勾选再问同一个问题，模型会给出通用回答且没有出处——这一步最能说明 RAG 的作用

### 效果评估

`scripts/eval_ai.py` 用固定题集（33 道问答 + 3 轮出题）跑一遍端到端流程，结果写入 `docs/eval-report.md`：

```powershell
.venv\Scripts\python.exe scripts\eval_ai.py
```

脚本使用独立的临时数据库，不会污染 `studymate.db`。本机（RTX 4060 Laptop + Qwen2.5-3B Q4）实测结果：

| 指标 | 结果 |
| --- | --- |
| 检索命中率（top-4 含正确文档） | 85% |
| Top-1 命中率（相似度最高即正确文档） | 58% |
| 回答关键词覆盖率 | 85% |
| 检索与关键词同时满足 | 85% |
| 平均问答延迟 | 6.3 s |
| 出题结构合法率（4 选项且答案合法） | 100% |
| 出题重复（同题干） | 0 / 9 |

语料是 6 篇课程笔记（数据结构 / 番茄工作法 / 梯度下降 / HTTP 与 REST / 数据库索引），每篇 1 个文本块，`TOP_K=4`。33 题里没命中的 5 题集中在「数据库索引」和少数边界问法上：模型会诚实回答「资料中没有相关内容」，而不是编造——这符合 RAG 的预期行为，但检索召回还有提升空间。

一个实测出来的细节：`nomic-embed-text` 是按「任务前缀」训练的，入库文本要加 `search_document: `、检索问题要加 `search_query: `，之前不加前缀时关键词覆盖率只有 76%，加上后升到 85%。换 embedding 模型或改了前缀策略后，用 `scripts/reindex_embeddings.py` 把已有资料的向量重算一遍即可：

```powershell
.venv\Scripts\python.exe scripts\reindex_embeddings.py
```

如果要继续提升中文检索效果，下一步是把向量模型换成 `bge-m3`（多语言，中文明显更强），前端与接口都不用改。

## 后续改进方向

- 增加用户注册、登录和个人数据隔离
- 扩充后端接口测试及前端功能测试
- 完善输入校验、异常处理与用户反馈
- 优化移动端适配和页面交互体验
- 探索线上部署方案

以上为后续改进方向，不代表这些功能已经完成。

## 项目目的

通过开发 StudyMate，实践和巩固：

- 前后端分离架构设计
- REST API 设计与调用
- Python 后端开发
- React 与 TypeScript 前端开发
- 关系型数据库与 ORM 操作
- 前端状态管理
- 自动化测试与持续集成
- Git 版本控制和 GitHub 项目管理
