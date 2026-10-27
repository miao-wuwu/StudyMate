import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import "./AgentPanel.css";

const API_URL = "http://127.0.0.1:8000";

type Step = {
  index: number;
  thought: string;
  tool: string;
  args: Record<string, unknown>;
  observation: string;
  error: string;
  elapsed_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
};

type Totals = {
  steps: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  elapsed_ms: number;
};

type Source = { index: number; title: string; seq: number; score: number; content?: string };

type RunResult = {
  answer: string;
  fallback: boolean;
  fallback_reason?: string;
  mode: string;
  sources?: Source[];
  steps: Step[];
  totals: Totals;
  tools_used: string[];
  model?: string;
};

type ToolSpec = { name: string; description: string; parameters: unknown };

type Run = {
  id: number;
  question: string;
  status: "running" | "done" | "error";
  steps: Step[];
  result?: RunResult;
  error?: string;
  draftAnswer?: string;
  startedAt: number;
};

type HealthInfo = {
  ok: boolean;
  provider: string;
  model: string;
  detail?: string;
};

function fmtMs(ms: number): string {
  if (!ms) return "-";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function clip(text: string, max = 220): string {
  const flat = (text || "").replace(/\s+/g, " ").trim();
  return flat.length <= max ? flat : `${flat.slice(0, max)}…`;
}

/** 把 SSE 的 body 解析成事件对象流 */
async function readSSE(
  response: Response,
  onEvent: (event: Record<string, unknown>) => void,
  signal: AbortSignal,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("浏览器不支持流式读取");
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    if (signal.aborted) {
      await reader.cancel();
      return;
    }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const payload = line.slice(6).trim();
      if (payload === "[DONE]") return;
      try {
        onEvent(JSON.parse(payload) as Record<string, unknown>);
      } catch {
        // 半截 JSON 忽略
      }
    }
  }
}

function AgentPanel() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [input, setInput] = useState("");
  const [maxSteps, setMaxSteps] = useState(5);
  const [running, setRunning] = useState(false);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const nextId = useRef(1);

  const loadHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/ai/health`);
      setHealth(response.ok ? ((await response.json()) as HealthInfo) : null);
    } catch {
      setHealth(null);
    }
  }, []);

  const loadTools = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/ai/agent/tools`);
      if (!response.ok) throw new Error("读取工具失败");
      const data = (await response.json()) as { tools: ToolSpec[] };
      setTools(data.tools ?? []);
    } catch {
      setTools([]);
    }
  }, []);

  useEffect(() => {
    void loadHealth();
    void loadTools();
  }, [loadHealth, loadTools]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [runs]);

  const patchRun = (id: number, patch: (run: Run) => Run) => {
    setRuns((prev) => prev.map((run) => (run.id === id ? patch(run) : run)));
  };

  const submit = async () => {
    const question = input.trim();
    if (!question || running) return;
    const id = nextId.current++;
    setInput("");
    setRunning(true);
    setRuns((prev) => [...prev, { id, question, status: "running", steps: [], startedAt: Date.now() }]);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await fetch(`${API_URL}/ai/agent/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, max_steps: maxSteps }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      await readSSE(
        response,
        (event) => {
          const type = String(event.type ?? "");
          if (type === "step") {
            const step = event.step as Step;
            patchRun(id, (run) => ({ ...run, steps: [...run.steps, step] }));
          } else if (type === "final") {
            patchRun(id, (run) => ({ ...run, draftAnswer: String(event.answer ?? "") }));
          } else if (type === "result") {
            const result = event.result as RunResult;
            patchRun(id, (run) => ({ ...run, status: "done", result, steps: result.steps ?? run.steps }));
          } else if (type === "error") {
            patchRun(id, (run) => ({ ...run, status: "error", error: String(event.message ?? "未知错误") }));
          } else if (type === "fallback") {
            patchRun(id, (run) => ({ ...run, error: `降级：${String(event.reason ?? "")}` }));
          }
        },
        controller.signal,
      );
      patchRun(id, (run) => (run.status === "running" ? { ...run, status: "done" } : run));
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        patchRun(id, (run) => ({ ...run, status: "done", error: "已手动停止" }));
      } else {
        patchRun(id, (run) => ({ ...run, status: "error", error: (err as Error).message }));
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  };

  const stop = () => {
    abortRef.current?.abort();
  };

  const toggle = (key: string) => setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));

  const examples = [
    "我的资料库里有哪些内容？",
    "反向传播是怎么工作的？",
    "帮我把最近的笔记出成 3 道选择题",
  ];

  return (
    <section className="agent-page">
      <header className="agent-hero">
        <div>
          <p className="agent-kicker">Agent · 规划 + 工具调用</p>
          <h2>会自己查资料的学习助理</h2>
          <p>
            它会先想清楚要查什么，再调用检索 / 摘要 / 出题工具，拿到结果后判断够不够，
            够了才回答。每一步耗时与 token 都记在下面——调不动时会自动降级成普通问答，不会给你空白。
          </p>
        </div>
        <div className={`agent-status ${health?.ok ? "online" : ""}`}>
          <span className="agent-status-dot" />
          <div>
            <strong>{health?.ok ? health.model : "模型未就绪"}</strong>
            <small>{health?.ok ? `${health.provider} · ${tools.length} 个工具` : health?.detail || "checking…"}</small>
          </div>
        </div>
      </header>

      <div className="agent-layout">
        <div className="agent-tools-card">
          <h3>可用工具</h3>
          <ul>
            {tools.map((tool) => (
              <li key={tool.name}>
                <code>{tool.name}</code>
                <span>{tool.description}</span>
              </li>
            ))}
            {!tools.length && <li className="agent-muted">未读取到工具（后端没启动？）</li>}
          </ul>
        </div>

        <div className="agent-chat-card">
          <div className="agent-run-list" ref={listRef}>
            {!runs.length && (
              <div className="agent-empty">
                <p>试一个：</p>
                <div className="agent-examples">
                  {examples.map((example) => (
                    <button key={example} type="button" onClick={() => setInput(example)}>
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {runs.map((run) => (
              <article key={run.id} className="agent-run">
                <div className="agent-question">
                  <span className="agent-avatar">你</span>
                  <p>{run.question}</p>
                </div>

                {(run.steps.length > 0 || run.status === "running") && (
                  <ol className="agent-timeline">
                    {run.steps.map((step) => {
                      const key = `${run.id}-${step.index}`;
                      const open = expanded[key];
                      return (
                        <li key={step.index} className={step.error ? "has-error" : ""}>
                          <div className="agent-step-head">
                            <span className="agent-step-index">{step.index}</span>
                            {step.tool ? (
                              <code className="agent-tool-chip">{step.tool}</code>
                            ) : (
                              <em className="agent-muted">思考</em>
                            )}
                            <span className="agent-step-meta">
                              {fmtMs(step.elapsed_ms)} · {step.prompt_tokens + step.completion_tokens} tok
                            </span>
                          </div>
                          {step.thought && <p className="agent-thought">{step.thought}</p>}
                          {step.error && <p className="agent-step-error">⚠ {step.error}</p>}
                          {step.observation && (
                            <div className="agent-observation">
                              <button type="button" className="agent-link" onClick={() => toggle(key)}>
                                {open ? "收起观察结果" : "查看观察结果"}
                              </button>
                              <pre className={open ? "open" : ""}>{open ? step.observation : clip(step.observation, 120)}</pre>
                            </div>
                          )}
                        </li>
                      );
                    })}
                    {run.status === "running" && (
                      <li className="agent-typing">
                        <span className="agent-dot" />
                        <span className="agent-dot" />
                        <span className="agent-dot" />
                      </li>
                    )}
                  </ol>
                )}

                {run.result && (
                  <div className="agent-answer">
                    <div className="agent-answer-head">
                      <span className="agent-avatar">AI</span>
                      {run.result.fallback ? (
                        <span className="agent-badge warn">已降级 · {run.result.fallback_reason}</span>
                      ) : (
                        <span className="agent-badge ok">Agent 完成</span>
                      )}
                    </div>
                    <p className="agent-answer-text">{run.result.answer}</p>

                    {!!run.result.sources?.length && (
                      <ul className="agent-sources">
                        {run.result.sources.map((source) => (
                          <li key={`${source.index}-${source.title}-${source.seq}`}>
                            <span>[{source.index}]</span> {source.title} · 第 {source.seq + 1} 段
                            <em>{(source.score ?? 0).toFixed(2)}</em>
                          </li>
                        ))}
                      </ul>
                    )}

                    <div className="agent-metrics">
                      <span>步数 {run.result.totals.steps ?? run.result.steps.length}</span>
                      <span>tokens {run.result.totals.total_tokens ?? 0}</span>
                      <span>耗时 {fmtMs(run.result.totals.elapsed_ms)}</span>
                      <span>工具 {run.result.tools_used?.join(" / ") || "无"}</span>
                    </div>
                  </div>
                )}

                {run.status === "error" && <p className="agent-step-error">⚠ {run.error}</p>}
                {run.status === "done" && !run.result && run.draftAnswer && (
                  <p className="agent-answer-text">{run.draftAnswer}</p>
                )}
              </article>
            ))}
          </div>

          <div className="agent-input-row">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
                }
              }}
              placeholder="问点什么，比如「反向传播是怎么工作的」…（Enter 发送，Shift+Enter 换行）"
              rows={2}
              disabled={running}
            />
            <div className="agent-input-actions">
              <label>
                步数上限
                <select value={maxSteps} onChange={(event) => setMaxSteps(Number(event.target.value))} disabled={running}>
                  <option value={3}>3</option>
                  <option value={5}>5</option>
                  <option value={8}>8</option>
                </select>
              </label>
              {running ? (
                <button type="button" className="agent-stop" onClick={stop}>
                  停止
                </button>
              ) : (
                <button type="button" className="agent-send" onClick={() => void submit()} disabled={!input.trim()}>
                  运行
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default AgentPanel;