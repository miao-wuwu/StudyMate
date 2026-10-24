import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import "./AiPanel.css";

const API_URL = "http://127.0.0.1:8000";

type ChatRole = "user" | "assistant";

type ChatMessage = {
  id: number;
  role: ChatRole;
  content: string;
  sources?: AskSource[];
  mode?: string;
  elapsed?: number;
  kind?: MessageKind;
  points?: string[];
  quiz?: QuizItem[];
};

type AskSource = {
  index: number;
  title: string;
  seq: number;
  score: number;
};

type DocItem = {
  id: number;
  title: string;
  source: string;
  char_count: number;
  chunk_count: number;
  created_at: string;
};

type HealthInfo = {
  provider: string;
  model: string;
  embed_model: string;
  ok: boolean;
  detail?: string;
  model_loaded?: boolean;
  rag?: { documents: number; chunks: number; embedded: number };
};

type UploadResponse = {
  id: number;
  title: string;
  chunks: number;
  chars: number;
};

type QuizItem = {
  question: string;
  options: string[];
  answer: string;
  explanation: string;
};

type MessageKind = "text" | "summary" | "quiz";

/** 把后端返回的 JSON 错误体压成一行人话 */
function describeError(text: string): string {
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    const detail = parsed.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg: unknown }).msg) : ""))
        .filter(Boolean);
      if (msgs.length) return msgs.join("；");
    }
  } catch {
    // 不是 JSON，原样返回
  }
  return text;
}

function AiPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState<"summary" | "quiz" | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [useDocs, setUseDocs] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [docNotice, setDocNotice] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const nextId = useRef(1);

  const loadHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/ai/health`);
      if (!response.ok) throw new Error("健康检查失败");
      setHealth((await response.json()) as HealthInfo);
    } catch {
      setHealth(null);
    }
  }, []);

  const loadDocs = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/ai/documents`);
      if (!response.ok) throw new Error("读取资料失败");
      const data = (await response.json()) as { items: DocItem[] };
      setDocs(data.items ?? []);
    } catch {
      setDocs([]);
    }
  }, []);

  useEffect(() => {
    void loadHealth();
    void loadDocs();
  }, [loadHealth, loadDocs]);

  useEffect(() => {
    const node = listRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, sending]);

  const send = useCallback(async () => {
    const question = input.trim();
    if (!question || sending) return;

    setError("");
    setInput("");
    setSending(true);

    const userMessage: ChatMessage = {
      id: nextId.current++,
      role: "user",
      content: question,
    };
    const history = [...messages, userMessage];
    setMessages(history);
    // 只把有实际内容的轮次发给后端，避免半截历史（例如上一次失败）触发 422
    const payloadMessages = history
      .filter((item) => typeof item.content === "string" && item.content.trim())
      .map((item) => ({ role: item.role, content: item.content }));

    const started = Date.now();
    try {
      if (useDocs) {
        const response = await fetch(`${API_URL}/ai/ask`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        });
        if (!response.ok) throw new Error(await response.text());
        const data = (await response.json()) as {
          answer: string;
          mode: string;
          sources?: AskSource[];
        };
        setMessages((current) => [
          ...current,
          {
            id: nextId.current++,
            role: "assistant",
            content: data.answer,
            mode: data.mode,
            sources: data.sources ?? [],
            elapsed: (Date.now() - started) / 1000,
          },
        ]);
      } else {
        const response = await fetch(`${API_URL}/ai/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: payloadMessages }),
        });
        if (!response.ok) throw new Error(await response.text());
        const data = (await response.json()) as { reply?: string; answer?: string };
        const reply = data.reply ?? data.answer ?? "";
        setMessages((current) => [
          ...current,
          {
            id: nextId.current++,
            role: "assistant",
            content: reply || "（模型返回了空内容，请再试一次）",
            mode: "chat",
            elapsed: (Date.now() - started) / 1000,
          },
        ]);
      }
      void loadHealth();
    } catch (err) {
      const text = err instanceof Error ? err.message : String(err);
      setError(`调用失败：${describeError(text).slice(0, 200)}`);
    } finally {
      setSending(false);
    }
  }, [input, sending, useDocs, messages, loadHealth]);

  const runSummary = useCallback(async () => {
    if (busy !== null || sending) return;
    setError("");
    setBusy("summary");
    const started = Date.now();
    try {
      const response = await fetch(`${API_URL}/ai/summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_points: 5 }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as {
        summary: string;
        points?: string[];
        parsed?: boolean;
      };
      setMessages((current) => [
        ...current,
        {
          id: nextId.current++,
          role: "assistant",
          content: data.summary || "（模型没有返回摘要）",
          kind: "summary",
          points: data.points ?? [],
          mode: data.parsed === false ? "fallback" : "summary",
          elapsed: (Date.now() - started) / 1000,
        },
      ]);
      setPicked({});
      void loadHealth();
    } catch (err) {
      const text = err instanceof Error ? err.message : String(err);
      setError(`总结失败：${describeError(text).slice(0, 200)}`);
    } finally {
      setBusy(null);
    }
  }, [busy, sending, loadHealth]);

  const runQuiz = useCallback(async () => {
    if (busy !== null || sending) return;
    setError("");
    setBusy("quiz");
    const started = Date.now();
    try {
      const response = await fetch(`${API_URL}/ai/quiz`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: 3 }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data = (await response.json()) as { questions?: QuizItem[] };
      const questions = data.questions ?? [];
      setMessages((current) => [
        ...current,
        {
          id: nextId.current++,
          role: "assistant",
          content: questions.length
            ? `按资料出了 ${questions.length} 道题，选一下看看对不对。`
            : "模型没有给出可用的题目，再点一次试试。",
          kind: "quiz",
          quiz: questions,
          mode: "quiz",
          elapsed: (Date.now() - started) / 1000,
        },
      ]);
      setPicked({});
      void loadHealth();
    } catch (err) {
      const text = err instanceof Error ? err.message : String(err);
      setError(`出题失败：${describeError(text).slice(0, 200)}`);
    } finally {
      setBusy(null);
    }
  }, [busy, sending, loadHealth]);

  const upload = useCallback(
    async (file: File) => {
      setUploading(true);
      setDocNotice("");
      setError("");
      try {
        const form = new FormData();
        form.append("file", file);
        const response = await fetch(`${API_URL}/ai/documents/upload`, {
          method: "POST",
          body: form,
        });
        if (!response.ok) throw new Error(await response.text());
        const data = (await response.json()) as UploadResponse;
        setDocNotice(
          `已导入《${data.title}》：${data.chars} 字 / ${data.chunks} 段`
        );
        await loadDocs();
        await loadHealth();
      } catch (err) {
        const text = err instanceof Error ? err.message : String(err);
        setError(`导入失败：${text.slice(0, 200)}`);
      } finally {
        setUploading(false);
        if (fileRef.current) fileRef.current.value = "";
      }
    },
    [loadDocs, loadHealth]
  );

  const removeDoc = useCallback(
    async (id: number) => {
      try {
        const response = await fetch(`${API_URL}/ai/documents/${id}`, {
          method: "DELETE",
        });
        if (!response.ok) throw new Error("删除失败");
        await loadDocs();
        await loadHealth();
      } catch {
        setError("删除资料失败，请稍后重试。");
      }
    },
    [loadDocs, loadHealth]
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setError("");
  }, []);

  const ragStats = health?.rag;

  return (
    <section className="ai-page">
      <div className="ai-hero">
        <div>
          <span className="section-kicker">AI ASSISTANT</span>
          <h2>本地 AI 学习助手</h2>
          <p>
            模型跑在你自己电脑上，不联网、不上传数据；把笔记或讲义丢进资料库，它就能带着出处回答。
          </p>
        </div>

        <div className={`ai-status ${health?.ok ? "online" : "offline"}`}>
          <span className="ai-status-dot" />
          <div>
            <strong>{health?.ok ? "已连接本地模型" : "未连接到模型"}</strong>
            <small>
              {health
                ? `${health.model} · 向量 ${health.embed_model}`
                : "请确认 Ollama 正在运行"}
            </small>
          </div>
        </div>
      </div>

      <div className="ai-grid">
        <div className="ai-chat">
          <div className="ai-study-bar">
            <button
              type="button"
              disabled={busy !== null || sending}
              onClick={() => void runSummary()}
            >
              {busy === "summary" ? "正在总结…" : "总结资料"}
            </button>
            <button
              type="button"
              disabled={busy !== null || sending}
              onClick={() => void runQuiz()}
            >
              {busy === "quiz" ? "正在出题…" : "出 3 道题"}
            </button>
            <span>从资料库生成，点选项看对错</span>
          </div>

          <div className="ai-chat-heading">
            <h3>对话</h3>
            <div className="ai-chat-actions">
              <label className="ai-toggle">
                <input
                  type="checkbox"
                  checked={useDocs}
                  onChange={(event) => setUseDocs(event.target.checked)}
                />
                <span>结合资料回答</span>
              </label>
              <button type="button" onClick={clearChat} disabled={!messages.length}>
                清空
              </button>
            </div>
          </div>

          <div className="ai-messages" ref={listRef}>
            {messages.length === 0 ? (
              <div className="ai-empty">
                <p>试试这样问：</p>
                <ul>
                  <li>帮我梳理今天学的数据结构重点</li>
                  <li>番茄工作法每次专注多久？（先上传笔记再勾选「结合资料」）</li>
                  <li>用三道题考考我链表和数组的区别</li>
                </ul>
              </div>
            ) : (
              messages.map((item) => (
                <article key={item.id} className={`ai-msg ${item.role}`}>
                  <header>
                    <span>{item.role === "user" ? "我" : "助手"}</span>
                    {item.role === "assistant" && item.mode ? (
                      <em className={item.mode === "rag" ? "badge rag" : "badge"}>
                        {item.mode === "rag" ? "资料检索" : "通用对话"}
                      </em>
                    ) : null}
                    {item.elapsed ? <small>{item.elapsed.toFixed(1)}s</small> : null}
                  </header>
                  <p>{item.content}</p>
                  {item.kind === "summary" && item.points && item.points.length > 0 ? (
                    <ol className="ai-points">
                      {item.points.map((point, index) => (
                        <li key={`${item.id}-p${index}`}>{point}</li>
                      ))}
                    </ol>
                  ) : null}
                  {item.kind === "quiz" && item.quiz && item.quiz.length > 0 ? (
                    <div className="ai-quiz">
                      {item.quiz.map((question, qIndex) => {
                        const key = `${item.id}-${qIndex}`;
                        const choice = picked[key];
                        return (
                          <section key={key} className="ai-quiz-item">
                            <h4>
                              {qIndex + 1}. {question.question}
                            </h4>
                            <div className="ai-quiz-options">
                              {question.options.map((option, oIndex) => {
                                const letter = String.fromCharCode(65 + oIndex);
                                const isAnswer = letter === question.answer;
                                const isPicked = choice === letter;
                                const state = !choice
                                  ? ""
                                  : isAnswer
                                    ? "correct"
                                    : isPicked
                                      ? "wrong"
                                      : "muted";
                                return (
                                  <button
                                    key={`${key}-${letter}`}
                                    type="button"
                                    className={`ai-quiz-option ${state}`}
                                    disabled={Boolean(choice)}
                                    onClick={() =>
                                      setPicked((current) => ({ ...current, [key]: letter }))
                                    }
                                  >
                                    <b>{letter}</b>
                                    <span>{option}</span>
                                  </button>
                                );
                              })}
                            </div>
                            {choice ? (
                              <p className="ai-quiz-explain">
                                {choice === question.answer ? "✓ 答对了。" : `✗ 正确答案是 ${question.answer}。`}
                                {question.explanation}
                              </p>
                            ) : null}
                          </section>
                        );
                      })}
                    </div>
                  ) : null}
                  {item.sources && item.sources.length > 0 ? (
                    <div className="ai-sources">
                      {item.sources.map((source) => (
                        <span key={`${item.id}-${source.index}`}>
                          [{source.index}] 《{source.title}》第 {source.seq + 1} 段 ·
                          相似度 {source.score.toFixed(2)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))
            )}

            {sending ? (
              <article className="ai-msg assistant pending">
                <header>
                  <span>助手</span>
                </header>
                <p>正在思考…（首次调用需要加载模型，可能要 30 秒左右）</p>
              </article>
            ) : null}
          </div>

          {error ? <p className="ai-error">{error}</p> : null}

          <form
            className="ai-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <textarea
              value={input}
              rows={2}
              placeholder={
                useDocs
                  ? "基于资料提问，例如：番茄工作法每次专注多久？"
                  : "问点什么，例如：帮我出三道排序算法的练习题"
              }
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <button type="submit" disabled={sending || !input.trim()}>
              {sending ? "生成中" : "发送"}
            </button>
          </form>
        </div>

        <aside className="ai-docs">
          <div className="ai-docs-heading">
            <h3>资料库</h3>
            <span>
              {ragStats
                ? `${ragStats.documents} 篇 · ${ragStats.chunks} 段`
                : "0 篇"}
            </span>
          </div>

          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md,.markdown,.pdf"
            className="ai-file-input"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
          />

          <button
            type="button"
            className="ai-upload"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
          >
            {uploading ? "正在解析并向量化…" : "上传 PDF / Markdown / TXT"}
          </button>

          {docNotice ? <p className="ai-notice">{docNotice}</p> : null}

          <div className="ai-doc-list">
            {docs.length === 0 ? (
              <p className="ai-docs-empty">
                还没有资料。上传课堂讲义、读书笔记或课程 PDF，勾选「结合资料回答」后提问会带上出处。
              </p>
            ) : (
              docs.map((item) => (
                <article key={item.id} className="ai-doc-item">
                  <div>
                    <strong>{item.title}</strong>
                    <small>
                      {item.char_count} 字 · {item.chunk_count} 段 ·{" "}
                      {item.created_at.slice(5, 16).replace("T", " ")}
                    </small>
                  </div>
                  <button
                    type="button"
                    onClick={() => void removeDoc(item.id)}
                    aria-label={`删除 ${item.title}`}
                  >
                    删除
                  </button>
                </article>
              ))
            )}
          </div>

          <div className="ai-docs-tip">
            <h4>说明</h4>
            <ul>
              <li>解析在本机完成：PyMuPDF 抽文本 → 分块 → 向量化入库</li>
              <li>向量与笔记同库（studymate.db），删资料不影响笔记</li>
              <li>只支持文本型 PDF，扫描件需要先 OCR</li>
            </ul>
          </div>
        </aside>
      </div>
    </section>
  );
}

export default AiPanel;
