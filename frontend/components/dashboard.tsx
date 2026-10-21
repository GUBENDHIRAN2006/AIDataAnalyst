"use client";

import Link from "next/link";
import Papa from "papaparse";
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";

type Provider = "PostgreSQL" | "MySQL" | "MongoDB" | "Supabase";
type TableRef = { name: string; schema?: string | null };
type RecordRow = Record<string, unknown>;
type Account = { authenticated: boolean; email: string };
type HistoryItem = { id: string; title: string; question: string; answer: string; created_at: string };

const providers: Provider[] = ["PostgreSQL", "MySQL", "MongoDB", "Supabase"];
const MAX_WEB_DATA_BYTES = 3_500_000;

async function requestJson(path: string, init?: RequestInit) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail ?? "The request failed.");
  return data;
}

export default function Dashboard() {
  const [account, setAccount] = useState<Account>({ authenticated: false, email: "" });
  const [provider, setProvider] = useState<Provider>("PostgreSQL");
  const [connection, setConnection] = useState<Record<string, string | number | boolean>>({});
  const [tables, setTables] = useState<TableRef[]>([]);
  const [selectedTable, setSelectedTable] = useState("");
  const [records, setRecords] = useState<RecordRow[]>([]);
  const [filename, setFilename] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void fetch("/api/session", { cache: "no-store" })
      .then((response) => response.json())
      .then((value: Account) => setAccount(value))
      .catch(() => setAccount({ authenticated: false, email: "" }));
  }, []);

  const columns = useMemo(() => Object.keys(records[0] ?? {}), [records]);

  function changeProvider(next: Provider) {
    setProvider(next);
    setTables([]);
    setSelectedTable("");
    setConnection({});
    setError("");
    setNotice("");
  }

  function setField(name: string, value: string | number | boolean) {
    setConnection((current) => ({ ...current, [name]: value }));
  }

  async function discoverTables(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await requestJson("/api/backend/api/database/tables", {
        method: "POST",
        body: JSON.stringify({ provider, ...connection }),
      });
      setTables(result.tables as TableRef[]);
      setSelectedTable("");
      setNotice(`${result.tables.length} table(s) found. Select one to import.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Database connection failed.");
    } finally {
      setBusy(false);
    }
  }

  async function importTable() {
    const table = tables.find((item) => `${item.schema ?? ""}.${item.name}` === selectedTable);
    if (!table) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await requestJson("/api/backend/api/database/import", {
        method: "POST",
        body: JSON.stringify({ connection: { provider, ...connection }, table: table.name, schema: table.schema }),
      });
      const rowData = result.records as RecordRow[];
      if (new TextEncoder().encode(JSON.stringify(rowData)).byteLength > MAX_WEB_DATA_BYTES) {
        throw new Error("This dataset is too large for a Vercel request. Select a smaller table.");
      }
      setRecords(rowData);
      setFilename(String(result.filename ?? table.name));
      setAnswer("");
      setNotice(`Imported ${rowData.length.toLocaleString()} rows.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not import this table.");
    } finally {
      setBusy(false);
    }
  }

  function loadCsv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    setNotice("");
    if (file.size > MAX_WEB_DATA_BYTES) {
      setError("Choose a CSV up to 3.5 MB for this Vercel-powered interface.");
      event.target.value = "";
      return;
    }
    Papa.parse<RecordRow>(file, {
      header: true,
      dynamicTyping: true,
      skipEmptyLines: true,
      complete: (result) => {
        if (result.errors.length) {
          setError(result.errors[0].message);
          return;
        }
        if (!result.data.length) {
          setError("The CSV has no data rows.");
          return;
        }
        setRecords(result.data);
        setFilename(file.name);
        setAnswer("");
        setNotice(`Loaded ${result.data.length.toLocaleString()} rows from ${file.name}.`);
      },
      error: (reason) => setError(reason.message),
    });
  }

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const size = new TextEncoder().encode(JSON.stringify(records)).byteLength;
      if (size > MAX_WEB_DATA_BYTES) {
        throw new Error("This dataset is too large for Vercel. Select a smaller table.");
      }
      const result = await requestJson("/api/backend/api/analyze", {
        method: "POST",
        body: JSON.stringify({ question, records, filename }),
      });
      if (result.error) throw new Error(result.error);
      setAnswer(String(result.answer ?? "Analysis finished."));
      setNotice("Analysis complete.");
      if (account.authenticated) await loadHistory();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  async function loadHistory() {
    if (!account.authenticated) return;
    try {
      const result = await requestJson("/api/backend/api/history");
      setHistory(result.items as HistoryItem[]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load saved history.");
    }
  }

  async function signOut() {
    setBusy(true);
    try {
      await requestJson("/api/auth/logout", { method: "POST" });
      setAccount({ authenticated: false, email: "" });
      setHistory([]);
      setNotice("Signed out.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign out failed.");
    } finally {
      setBusy(false);
    }
  }

  const selectedProviderName = provider.toLowerCase();

  return (
    <div className="shell">
      <header className="topbar">
        <Link className="brand" href="/">
          <img className="brand-image" src="/brand.svg" alt="" /> AI Data Analyst
        </Link>
        <nav className="nav-links">
          <Link className="nav-link" href="/integrations">Integrations</Link>
          {account.authenticated ? (
            <>
              <span className="small">{account.email}</span>
              <button className="button-secondary" disabled={busy} onClick={signOut}>Sign out</button>
            </>
          ) : (
            <Link className="button-secondary" href="/login"><span className="person-icon">•</span>Sign in</Link>
          )}
        </nav>
      </header>

      <main className="page">
        <section className="hero">
          <div>
            <div className="eyebrow">Your data workspace</div>
            <h1>Connect data. Find answers.</h1>
            <p className="muted">Import a database table or CSV, then ask a question in plain language.</p>
          </div>
          <Link className="button-secondary" href="/integrations">Manage integrations →</Link>
        </section>

        {(error || notice) && <div className={`notice${error ? " error" : ""}`}>{error || notice}</div>}

        <section className="grid" style={{ marginTop: 20 }}>
          <article className="card span-8">
            <div className="row">
              <div><div className="eyebrow">Step 1</div><h2>Choose a data source</h2></div>
              <span className="small">Credentials stay in this browser session</span>
            </div>
            <div className="provider-grid">
              {providers.map((item) => (
                <button
                  key={item}
                  className={`provider${provider === item ? " active" : ""}`}
                  onClick={() => changeProvider(item)}
                  type="button"
                >
                  <span className="provider-mark">{item === "PostgreSQL" ? "PG" : item === "MySQL" ? "SQL" : item === "MongoDB" ? "MDB" : "SB"}</span><br />
                  {item}
                </button>
              ))}
            </div>
            <form className="form-grid" onSubmit={discoverTables}>
              {provider === "PostgreSQL" || provider === "MySQL" ? (
                <>
                  <div className="field"><label>Host</label><input required value={String(connection.host ?? "")} onChange={(event) => setField("host", event.target.value)} placeholder="db.example.com" /></div>
                  <div className="field"><label>Port</label><input required type="number" value={String(connection.port ?? (provider === "PostgreSQL" ? 5432 : 3306))} onChange={(event) => setField("port", Number(event.target.value))} /></div>
                  <div className="field"><label>Database</label><input required value={String(connection.database ?? "")} onChange={(event) => setField("database", event.target.value)} /></div>
                  <div className="field"><label>Username</label><input required value={String(connection.username ?? "")} onChange={(event) => setField("username", event.target.value)} /></div>
                  <div className="field"><label>Password</label><input required type="password" value={String(connection.password ?? "")} onChange={(event) => setField("password", event.target.value)} /></div>
                  <div className="field"><label><input type="checkbox" checked={connection.ssl !== false} onChange={(event) => setField("ssl", event.target.checked)} style={{ width: "auto", marginRight: 8 }} />Require TLS</label></div>
                </>
              ) : provider === "MongoDB" ? (
                <div className="field full"><label>MongoDB connection URI</label><input required type="password" value={String(connection.uri ?? "")} onChange={(event) => setField("uri", event.target.value)} placeholder="mongodb+srv://…" /></div>
              ) : (
                <>
                  <div className="field full"><label>Supabase project URL</label><input required value={String(connection.url ?? "")} onChange={(event) => setField("url", event.target.value)} placeholder="https://your-project.supabase.co" /></div>
                  <div className="field full"><label>Anon / publishable API key</label><input required type="password" value={String(connection.key ?? "")} onChange={(event) => setField("key", event.target.value)} /></div>
                  <div className="field full"><label>Optional user access token</label><input type="password" value={String(connection.access_token ?? "")} onChange={(event) => setField("access_token", event.target.value)} /></div>
                </>
              )}
              <div className="field full">
                <button className="button" disabled={busy} type="submit">{busy ? "Connecting…" : `Connect ${selectedProviderName} and list tables`}</button>
              </div>
            </form>
            {tables.length > 0 && (
              <div className="actions">
                <select aria-label="Table to import" value={selectedTable} onChange={(event) => setSelectedTable(event.target.value)}>
                  <option value="">Choose a table or collection</option>
                  {tables.map((table) => {
                    const value = `${table.schema ?? ""}.${table.name}`;
                    return <option key={value} value={value}>{table.schema ? `${table.schema}.` : ""}{table.name}</option>;
                  })}
                </select>
                <button className="button" disabled={!selectedTable || busy} onClick={importTable}>Import selected data</button>
              </div>
            )}
            <div className="notice">
              Use read-only credentials and trusted databases only. Avoid service-role keys. Vercel requests are limited to datasets around 3.5 MB in this starter integration.
            </div>
          </article>

          <article className="card span-4">
            <div className="eyebrow">Alternative</div>
            <h2>Upload a CSV</h2>
            <p className="muted">CSV files are parsed locally in your browser before analysis.</p>
            <div className="field" style={{ marginTop: 18 }}>
              <label htmlFor="csv-file">CSV file (up to 3.5 MB)</label>
              <input id="csv-file" type="file" accept=".csv,text/csv" onChange={loadCsv} />
            </div>
          </article>

          <article className="card span-8">
            <div className="row">
              <div><div className="eyebrow">Step 2</div><h2>Ask about your data</h2></div>
              <span className="small">{records.length.toLocaleString()} rows · {columns.length} columns</span>
            </div>
            {records.length ? (
              <>
                <div className="table-wrap">
                  <table>
                    <thead><tr>{columns.slice(0, 10).map((column) => <th key={column}>{column}</th>)}</tr></thead>
                    <tbody>{records.slice(0, 8).map((row, index) => <tr key={index}>{columns.slice(0, 10).map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}</tr>)}</tbody>
                  </table>
                </div>
                <form onSubmit={analyze}>
                  <div className="field" style={{ marginTop: 18 }}>
                    <label htmlFor="question">Your question</label>
                    <textarea id="question" required rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What are the main trends in this dataset?" />
                  </div>
                  <div className="actions"><button className="button" disabled={busy || !question.trim()} type="submit">{busy ? "Analyzing…" : "Analyze data"}</button></div>
                </form>
                {answer && <div className="answer">{answer}</div>}
              </>
            ) : (
              <p className="muted" style={{ marginTop: 20 }}>Connect a database or upload a CSV to preview rows and start analysis.</p>
            )}
          </article>

          <article className="card span-4">
            <div className="row">
              <div><div className="eyebrow">Your account</div><h2>Analysis history</h2></div>
            </div>
            {account.authenticated ? (
              <>
                <button className="button-secondary" style={{ marginTop: 16 }} onClick={loadHistory}>Load saved history</button>
                {history.map((item) => (
                  <details key={item.id} style={{ marginTop: 13 }}>
                    <summary style={{ cursor: "pointer", fontWeight: 700 }}>{item.title}</summary>
                    <p className="small">{item.question}</p>
                    <p className="small">{item.answer}</p>
                  </details>
                ))}
              </>
            ) : (
              <p className="muted" style={{ marginTop: 14 }}>Use as a guest, or <Link href="/login" style={{ color: "var(--brand)", fontWeight: 700 }}>sign in</Link> to save analysis history.</p>
            )}
          </article>
        </section>
      </main>
      <footer className="footer">AI Data Analyst · Supabase-backed accounts · FastAPI data services</footer>
    </div>
  );
}
