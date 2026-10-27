"""小规模评估：用固定题集量化 RAG 检索命中率与回答质量。

用法（在项目根目录）：
    .venv\\Scripts\\python.exe scripts\\eval_ai.py

脚本用独立的临时数据库，不会污染 studymate.db；跑完把结果打印成表格，
同时写到 docs/eval-report.md。
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine  # noqa: E402

from ai import config, llm, rag, store, study  # noqa: E402

REPORT = ROOT / "docs" / "eval-report.md"

DOCS: list[tuple[str, str]] = [
    (
        "栈与队列",
        "栈是后进先出（LIFO）的线性表，只能在栈顶插入和删除，push 与 pop 的时间复杂度都是 O(1)。\n"
        "队列是先进先出（FIFO），在队尾插入（enqueue）、队头删除（dequeue）。\n"
        "用两个栈可以实现队列：入队时压入栈 A；出队时如果栈 B 为空，就把 A 的元素全部倒入 B，"
        "再从 B 弹出。每个元素最多被移动两次，所以均摊时间复杂度是 O(1)。\n"
        "循环队列用取模运算复用数组空间，为了区分队空与队满，通常牺牲一个存储单元，"
        "或者额外记录当前元素个数。",
    ),
    (
        "番茄工作法",
        "番茄工作法把工作切成 25 分钟一个番茄钟，中间休息 5 分钟，四个番茄钟之后休息 15 到 30 分钟。\n"
        "它的核心不是计时器，而是把注意力范围缩小到一件事：番茄钟内不允许切换任务，"
        "被打断就把番茄作废重新开始。\n"
        "记录时只需要三类数据：计划番茄数、实际完成数、被打断次数。连续完成四个番茄钟算一轮。",
    ),
    (
        "梯度下降与学习率",
        "梯度下降沿负梯度方向更新参数：θ = θ - η * ∇L(θ)，其中 η 是学习率。\n"
        "学习率太大会震荡甚至发散，太小则收敛很慢；常见做法是先用较大学习率快速下降，"
        "再按 StepLR、Cosine 或 ReduceLROnPlateau 等策略衰减。\n"
        "随机梯度下降（SGD）每次只用一个批次估计梯度，噪声大但能跳出局部极小；"
        "加入动量项 momentum 可以平滑更新方向，常用取值 0.9。\n"
        "Adam 结合了动量与自适应学习率，收敛快，但在部分任务上泛化不如调好的 SGD。",
    ),
    (
        "链表与数组",
        "数组在内存里是一段连续空间，靠下标做偏移计算，所以随机访问是 O(1)；"
        "代价是插入和删除要搬移元素，最坏 O(n)，而且扩容要整体复制。\n"
        "链表由节点组成，节点分散存放、靠指针串起来：已知位置插入和删除只要改指针，是 O(1)，"
        "但想访问第 k 个元素必须从头遍历，是 O(n)。\n"
        "双向链表每个节点多存一个 prev（前驱）指针，换来回退遍历的便利。\n"
        "哨兵节点（dummy head/tail）把空链表和边界情况统一掉，省去大量判空分支。\n"
        "链表对 CPU 缓存不友好，因为节点不连续，所以实际常数往往比数组大。",
    ),
    (
        "HTTP 与 REST",
        "常用方法有 GET、POST、PUT、PATCH、DELETE。幂等性指同一请求重复执行，服务器状态结果一致："
        "GET、PUT、DELETE 幂等，POST 不幂等（重复提交会创建多条记录）。\n"
        "常见状态码：创建资源成功 201，删除或更新后无返回体 204，参数错误 400，"
        "未认证 401，已认证但无权限 403，资源不存在 404，冲突 409，"
        "请求体字段校验失败 422，服务端异常 500，上游依赖失败 502。\n"
        "REST 风格要求路径用名词复数表示资源，例如 /notes、/tasks，动作通过 HTTP 方法表达，"
        "而不是写在路径里。列表接口建议用 limit 与 offset 做分页。",
    ),
    (
        "数据库索引",
        "MySQL InnoDB 的索引主体是 B+ 树：非叶子节点只存键，叶子节点存数据并用链表相连，"
        "所以范围查询很快。\n"
        "聚簇索引按主键组织整行数据；二级索引只存索引列加主键，查非索引列需要回表。"
        "如果查询的列全在索引里就是覆盖索引，可以避免回表。\n"
        "联合索引遵循最左前缀原则：建了 (a, b)，能命中 a 或 a+b，单独查 b 用不上。\n"
        "索引失效的常见原因：前导模糊匹配 like '%x'、在索引列上套函数或做运算、"
        "发生隐式类型转换（字符串列传数字）、以及区分度太低。",
    ),
]

# (问题, 期望命中的文档标题, 回答里应当出现的关键词)
CASES: list[tuple[str, str, list[str]]] = [
    ("用两个栈实现队列，出队时怎么操作？", "栈与队列", ["倒"]),
    ("两个栈实现队列的均摊时间复杂度是多少？", "栈与队列", ["O(1)"]),
    ("循环队列怎么区分队空和队满？", "栈与队列", ["牺牲", "存储单元"]),
    ("栈的插入和删除在哪个位置进行？", "栈与队列", ["栈顶"]),
    ("队列的插入和删除分别在哪一端？", "栈与队列", ["队尾", "队头"]),
    ("栈和队列的根本区别是什么？", "栈与队列", ["后进先出", "先进先出"]),
    ("一个番茄钟是多长时间？", "番茄工作法", ["25"]),
    ("四个番茄钟之后休息多久？", "番茄工作法", ["15"]),
    ("番茄钟被打断以后怎么处理？", "番茄工作法", ["作废", "重新"]),
    ("番茄工作法需要记录哪三类数据？", "番茄工作法", ["计划", "实际", "打断"]),
    ("梯度下降的更新公式是什么？", "梯度下降与学习率", ["θ", "∇"]),
    ("学习率太大会出现什么问题？", "梯度下降与学习率", ["震荡", "发散"]),
    ("动量项的常用取值是多少？", "梯度下降与学习率", ["0.9"]),
    ("Adam 和 SGD 各有什么优缺点？", "梯度下降与学习率", ["泛化"]),
    ("SGD 的梯度噪声大反而有什么好处？", "梯度下降与学习率", ["局部极小"]),
    ("数组随机访问一个元素的时间复杂度是多少？", "链表与数组", ["O(1)"]),
    ("链表为什么随机访问慢？", "链表与数组", ["指针", "遍历"]),
    ("双向链表比单链表多存了什么？", "链表与数组", ["前驱"]),
    ("哨兵节点解决了什么问题？", "链表与数组", ["判空"]),
    ("数组和链表在内存布局上有什么区别？", "链表与数组", ["连续", "分散"]),
    ("为什么链表对 CPU 缓存不友好？", "链表与数组", ["连续", "缓存"]),
    ("GET 和 POST 在幂等性上有什么区别？", "HTTP 与 REST", ["幂等"]),
    ("哪些 HTTP 方法应该是幂等的？", "HTTP 与 REST", ["PUT", "DELETE"]),
    ("创建资源成功一般返回哪个状态码？", "HTTP 与 REST", ["201"]),
    ("401 和 403 的区别是什么？", "HTTP 与 REST", ["认证", "权限"]),
    ("请求体字段校验失败用哪个状态码？", "HTTP 与 REST", ["422"]),
    ("REST 风格里资源路径怎么命名？", "HTTP 与 REST", ["名词", "复数"]),
    ("列表接口一般怎么做分页？", "HTTP 与 REST", ["limit", "offset"]),
    ("MySQL 的索引一般用什么数据结构？", "数据库索引", ["B+"]),
    ("联合索引 (a,b) 只查 b 能走索引吗？", "数据库索引", ["最左"]),
    ("哪些写法会让索引失效？", "数据库索引", ["函数", "类型"]),
    ("覆盖索引为什么快？", "数据库索引", ["回表"]),
    ("聚簇索引和二级索引有什么区别？", "数据库索引", ["主键", "回表"]),
]


def prepare_corpus() -> None:
    tmp_db = Path(tempfile.gettempdir()) / "studymate-eval.db"
    tmp_db.unlink(missing_ok=True)
    store.engine = create_engine(f"sqlite:///{tmp_db}", connect_args={"check_same_thread": False})
    store.init_db()
    for title, text in DOCS:
        chunks = store.chunk_text(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        vectors = llm.embed(chunks)
        store.add_document(title=title, content=text, source="eval", vectors=vectors)
    print(f"语料已入库：{len(DOCS)} 篇 / {store.stats()['chunks']} 块")


def run_rag() -> tuple[list[dict], float]:
    rows: list[dict] = []
    latencies: list[float] = []
    for question, expected_title, keywords in CASES:
        started = time.time()
        try:
            result = rag.ask(question)
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            top_title = sources[0]["title"] if sources else ""
            hit = any(source["title"] == expected_title for source in sources)
            keyword_hit = all(word in answer for word in keywords)
        except Exception as exc:  # noqa: BLE001
            answer, top_title, hit, keyword_hit = f"<出错：{exc}>", "", False, False
        elapsed = time.time() - started
        latencies.append(elapsed)
        rows.append(
            {
                "question": question,
                "expected": expected_title,
                "top1": top_title,
                "retrieval": hit,
                "keyword": keyword_hit,
                "seconds": elapsed,
                "answer": answer.replace("\n", " ")[:120],
            }
        )
        print(
            f"  {'✓' if hit and keyword_hit else '×'} {question[:24]:<26}"
            f" 检索{'命中' if hit else '未中'} 关键词{'覆盖' if keyword_hit else '缺失'} {elapsed:4.1f}s"
        )
    return rows, statistics.mean(latencies)


def run_quiz(rounds: int = 3, count: int = 3) -> dict:
    valid = 0
    total = 0
    duplicate = 0
    seen: set[str] = set()
    for index in range(rounds):
        result = study.quiz(document_id=None, count=count)
        questions = result.get("questions", [])
        for item in questions:
            total += 1
            if item["answer"] in {"A", "B", "C", "D"} and len(item["options"]) == 4:
                valid += 1
            key = "".join(item["question"].split())
            if key in seen:
                duplicate += 1
            seen.add(key)
        print(f"  第 {index + 1} 轮：{len(questions)} 题，parsed={result.get('parsed')}")
    return {"total": total, "valid": valid, "duplicate": duplicate, "rounds": rounds}


def write_report(rows: list[dict], mean_latency: float, quiz_stats: dict) -> None:
    retrieval = sum(1 for row in rows if row["retrieval"]) / len(rows)
    top1 = sum(1 for row in rows if row["top1"] == row["expected"]) / len(rows)
    keyword = sum(1 for row in rows if row["keyword"]) / len(rows)
    both = sum(1 for row in rows if row["retrieval"] and row["keyword"]) / len(rows)
    valid_rate = quiz_stats["valid"] / quiz_stats["total"] if quiz_stats["total"] else 0

    lines = [
        "# AI 模块评估报告",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M')}",
        f"- 模型：{config.OLLAMA_MODEL}（Ollama）· 向量：{config.OLLAMA_EMBED_MODEL}",
        f"- 语料：{len(DOCS)} 篇课程笔记，共 {store.stats()['chunks']} 个文本块",
        f"- 题集：{len(rows)} 道问答 + {quiz_stats['rounds']} 轮出题",
        "",
        "## 汇总",
        "",
        "| 指标 | 结果 |",
        "| --- | --- |",
        f"| 检索命中率（top-4 含正确文档） | {retrieval:.0%} |",
        f"| Top-1 命中率（相似度最高就是正确文档） | {top1:.0%} |",
        f"| 回答关键词覆盖率 | {keyword:.0%} |",
        f"| 检索与关键词同时满足 | {both:.0%} |",
        f"| 平均问答延迟 | {mean_latency:.1f} s |",
        f"| 出题结构合法率（4 选项且答案合法） | {valid_rate:.0%} |",
        f"| 出题重复（同题干） | {quiz_stats['duplicate']} / {quiz_stats['total']} |",
        "",
        "## 明细",
        "",
        "| 问题 | 期望文档 | Top-1 | 检索 | 关键词 | 耗时 | 回答摘录 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['question']} | {row['expected']} | {row['top1'] or '—'} | "
            f"{'✓' if row['retrieval'] else '×'} | {'✓' if row['keyword'] else '×'} | "
            f"{row['seconds']:.1f}s | {row['answer']} |"
        )
    lines += [
        "",
        "> 说明：关键词覆盖是粗粒度指标，只检查回答里是否出现关键数字或术语，"
        "不代表表述完全正确；出题质量另需人工抽查（3B 模型仍可能出现多个选项同时成立）。",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入：{REPORT}")


def main() -> None:
    print("== 准备语料 ==")
    prepare_corpus()
    print("\n== 问答 ==")
    rows, mean_latency = run_rag()
    print("\n== 出题 ==")
    quiz_stats = run_quiz()
    write_report(rows, mean_latency, quiz_stats)
    print("\n完成")


if __name__ == "__main__":
    main()
