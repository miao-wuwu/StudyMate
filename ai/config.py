# -*- coding: utf-8 -*-
"""配置读取：优先环境变量，其次项目根目录的 .env 文件。

不引入 python-dotenv，用一个 20 行的最小解析器，避免多一个运行时依赖。
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "studymate.db"


def load_env_file(path: Path = BASE_DIR / ".env") -> None:
    """把 .env 里的键值对塞进 os.environ（已存在的环境变量优先，不覆盖）。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

# 提供方：ollama（本地、零成本） / deepseek（云端、要 key）
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

# 本地 Ollama
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "studymate-qwen")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# 云端 DeepSeek（可选）
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# 推理参数
NUM_CTX = int(os.getenv("LLM_NUM_CTX", "4096"))
KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "5m")  # 空闲 5 分钟卸载显存
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
REQUEST_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))

# 对话历史裁剪：留出上下文给模型回答，避免多轮之后超出 num_ctx
HISTORY_MAX_CHARS = int(os.getenv("LLM_HISTORY_MAX_CHARS", "6000"))
HISTORY_MAX_MESSAGES = int(os.getenv("LLM_HISTORY_MAX_MESSAGES", "20"))

# 文档问答（RAG）参数
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "80"))
TOP_K = int(os.getenv("RAG_TOP_K", "4"))

# 资料里没有答案时，是否允许补一段「通用知识」（明确标注、不带引用编号）
GENERAL_FALLBACK = os.getenv("AI_GENERAL_FALLBACK", "1").strip().lower() not in {"0", "false", "no"}
