"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import AnalysisOutput from "@/components/analysis-output";
import {
  ChatMessage,
  clearWorkspace,
  RecordRow,
  readWorkspace,
  Workspace,
  writeWorkspace,
} from "@/lib/workspace";

type Account = { authenticated: boolean; email: string };
type HistoryItem = { id: string; title: string; question: string; answer: string; created_at: string };
const MAX_WEB_DATA_BYTES = 2_900_000;

async function requestJson(path: string, init?: RequestInit) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "The request failed.");
  }
  return data;
}

function newMessage(role: ChatMessage["role"], content: string): ChatMessage {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    role,
    content,
    createdAt: new Date().toISOString(),
  };
}

export default function ChatWorkspace() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [account, setAccount] = useState<Account>({ authenticated: false, email: "" });
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const endOfChat = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void readWorkspace()
      .then((stored) => {
        if (!stored?.records.length) {
          setError("No dataset is ready. Return to the workspace, upload a CSV or connect a table, then start analysis.");
          return;
        }
        setWorkspace(stored);
        setMessages(stored.messages ?? []);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Could not load the local dataset.");
      })
      .finally(() => setLoading(false));

    void fetch("/api/session", { cache: "no-store" })
      .then((response) => response.json())
      .then((value: Account) => {
        setAccount(value);
        if (value.authenticated) {
          return requestJson("/api/backend/api/history").then((result) => {
            setHistory(result.items as HistoryItem[]);
          });
        }
        return undefined;
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    endOfChat.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspace || !question.trim() || busy) return;

    const prompt = question.trim();
    const userMessage = newMessage("user", prompt);
    const priorMessages = messages;
    const nextMessages = [...priorMessages, userMessage];
    setMessages(nextMessages);
    setQuestion("");
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const serializedRecords = JSON.stringify(workspace.records);
      if (new TextEncoder().encode(serializedRecords).byteLength > MAX_WEB_DATA_BYTES) {
        throw new Error("This dataset exceeds the 2.9 MB request limit. Return home and choose a smaller file or table.");
      }
      const result = await requestJson("/api/backend/api/analyze", {
        method: "POST",
        body: JSON.stringify({
          question: prompt,
          records: workspace.records,
          filename: workspace.filename,
          conversation_history: priorMessages
            .filter((message) => !message.error && message.content)
            .slice(-6)
            .map(({ role, content }) => ({ role, content: content.slice(-4000) })),
        }),
      });
      const assistantMessage: ChatMessage = {
        ...newMessage("assistant", String(result.answer ?? "")),
        tables: Array.isArray(result.tables) ? result.tables : [],
        charts: Array.isArray(result.charts) ? result.charts : [],
        warnings: Array.isArray(result.warnings) ? result.warnings : [],
        error: Boolean(result.error),
      };
      if (result.error) assistantMessage.content = String(result.error);
      const completedMessages = [...nextMessages, assistantMessage];
      setMessages(completedMessages);
      if (assistantMessage.error) setError("The analysis request needs attention; see the message below.");
      else setNotice("Analysis complete.");
      try {
        await writeWorkspace({ ...workspace, messages: completedMessages });
      } catch {
        setNotice("Analysis finished, but this conversation could not be saved in this browser.");
      }

      if (account.authenticated) {
        try {
          const historyResult = await requestJson("/api/backend/api/history");
          setHistory(historyResult.items as HistoryItem[]);
        } catch {
          setError("Analysis finished, but saved account history could not be refreshed.");
        }
      }
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Analysis failed.";
      setError(detail);
      const failedMessages = [
        ...nextMessages,
        { ...newMessage("assistant", detail), error: true },
      ];
      setMessages(failedMessages);
      try {
        await writeWorkspace({ ...workspace, messages: failedMessages });
      } catch {
        setNotice("The conversation could not be saved in this browser.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function startNewAnalysis() {
    try {
      await clearWorkspace();
      window.location.assign("/");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not clear the local workspace.");
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <Link className="brand" href="/">
          <img className="brand-image" src="/brand.svg" alt="" /> AI Data Analyst
        </Link>
        <nav className="nav-links">
          <Link className="nav-link" href="/">Workspace</Link>
          <Link className="nav-link" href="/integrations">Integrations</Link>
          {account.authenticated
            ? <span className="small">{account.email}</span>
            : <Link className="button-secondary" href="/login">Sign in</Link>}
        </nav>
      </header>

      <main className="page chat-page">
        <section className="hero chat-hero">
          <div>
            <div className="eyebrow">AI data analysis</div>
            <h1>{workspace?.filename ?? "Analysis chat"}</h1>
            <p className="muted">
              {workspace
                ? `${workspace.records.length.toLocaleString()} rows · ${Object.keys(workspace.records[0] ?? {}).length} columns · Ask follow-up questions in this conversation.`
                : "Prepare a dataset in your workspace to begin."}
            </p>
          </div>
          <button className="button-secondary" onClick={startNewAnalysis} disabled={busy}>Start new analysis</button>
        </section>

        {error && !messages.length && <div className="notice error">{error}</div>}
        {notice && <div className="notice">{notice}</div>}

        <div className="chat-layout">
          <section className="card chat-card" aria-label="Analysis conversation">
            <div className="chat-thread" aria-live="polite">
              {loading ? (
                <p className="muted">Loading your local dataset…</p>
              ) : messages.length ? messages.map((message) => (
                <article key={message.id} className={`chat-message ${message.role}`}>
                  <div className="chat-role">{message.role === "user" ? "You" : "AI Data Analyst"}</div>
                  {message.role === "assistant"
                    ? <AnalysisOutput message={message} />
                    : <div className="chat-user-text">{message.content}</div>}
                </article>
              )) : (
                <div className="chat-empty">
                  <h2>Ask a question about your data</h2>
                  <p className="muted">Ask for calculations, trends, comparisons, data quality, or charts. Follow up naturally.</p>
                  <div className="suggestions">
                    {["Summarize this dataset", "Show total sales by country", "Compare the top categories"].map((suggestion) => (
                      <button key={suggestion} className="button-secondary" onClick={() => setQuestion(suggestion)} disabled={!workspace}>
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {busy && <div className="chat-typing" role="status">Analyzing your data…</div>}
              <div ref={endOfChat} />
            </div>

            <form className="chat-composer" onSubmit={sendMessage}>
              <label htmlFor="chat-question">Your question</label>
              <div className="composer-row">
                <textarea
                  id="chat-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Ask a question or follow up on an earlier answer…"
                  rows={3}
                  maxLength={4000}
                  disabled={!workspace || busy}
                  required
                />
                <button className="button" type="submit" disabled={!workspace || busy || !question.trim()}>
                  {busy ? "Working…" : "Send"}
                </button>
              </div>
              <p className="small">Your dataset remains in this browser workspace. Datasets are limited to about 2.9 MB for analysis requests.</p>
            </form>
          </section>

          <aside className="chat-sidebar">
            <section className="card">
              <div className="eyebrow">Current dataset</div>
              <h2>Data preview</h2>
              {workspace ? (
                <>
                  <p className="small">{workspace.records.length.toLocaleString()} rows · {Object.keys(workspace.records[0] ?? {}).length} columns</p>
                  <div className="table-wrap preview-table">
                    <table>
                      <thead><tr>{Object.keys(workspace.records[0] ?? {}).slice(0, 5).map((column) => <th key={column}>{column}</th>)}</tr></thead>
                      <tbody>
                        {workspace.records.slice(0, 5).map((row, index) => (
                          <tr key={index}>
                            {Object.keys(workspace.records[0] ?? {}).slice(0, 5).map((column) => (
                              <td key={column}>{String((row as RecordRow)[column] ?? "")}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : <p className="muted">No dataset loaded.</p>}
            </section>

            {account.authenticated && (
              <section className="card">
                <div className="eyebrow">Your account</div>
                <h2>Saved history</h2>
                {history.length ? history.slice(0, 8).map((item) => (
                  <details className="saved-history-item" key={item.id}>
                    <summary>{item.title}</summary>
                    <p className="small">{item.question}</p>
                    <p className="small">{item.answer}</p>
                  </details>
                )) : <p className="muted">No saved analyses yet.</p>}
              </section>
            )}
          </aside>
        </div>
      </main>
    </div>
  );
}
