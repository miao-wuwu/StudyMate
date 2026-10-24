"""用当前的 embedding 配置重算资料库里所有分块的向量。

什么时候需要跑：

- 换了 `OLLAMA_EMBED_MODEL`
- 改动了向量前缀策略（例如 nomic-embed-text 的 search_document / search_query）
- 从备份恢复了旧的 studymate.db

用法：
    python -m scripts.reindex_embeddings        # 或 python scripts/reindex_embeddings.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai import llm, store  # noqa: E402


def main() -> int:
    store.init_db()
    documents = store.list_documents()
    if not documents:
        print("资料库是空的，没有需要重建向量的文档。")
        return 0

    total_chunks = 0
    for doc in documents:
        chunks = store.list_chunks(doc["id"])
        if not chunks:
            continue
        vectors = llm.embed([c["content"] for c in chunks], kind="document")
        count = store.update_chunk_vectors(doc["id"], vectors)
        total_chunks += count
        print(f"重建 《{doc['title']}》 分块 {count} 个")

    print(f"完成：{len(documents)} 篇文档 / {total_chunks} 个分块，维度 {len(vectors[0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
