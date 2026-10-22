"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    setBusy(true);
    try {
      const response = await fetch(`/api/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail ?? "Authentication failed.");
      if (result.requires_email_confirmation) {
        setMessage("Account created. Confirm your email, then sign in.");
      } else {
        router.push("/");
        router.refresh();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not connect to the backend.");
    } finally {
      setBusy(false);
      setPassword("");
    }
  }

  return (
    <main className="auth-wrap">
      <section className="card auth-card">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <Link className="brand" href="/">
            <img className="brand-image" src="/brand.svg" alt="" />
            AI Data Analyst
          </Link>
          <Link className="nav-link" href="/chat">Chat</Link>
        </div>
        <p className="eyebrow" style={{ marginTop: 30 }}>
          {mode === "login" ? "Welcome back" : "Get started"}
        </p>
        <h1 style={{ fontSize: 30 }}>
          {mode === "login" ? "Sign in to your account" : "Create your account"}
        </h1>
        <p className="muted">
          {mode === "login"
            ? "Sign in to access your saved analysis history."
            : "Create an account to keep your analysis history with you."}
        </p>
        <form className="form-grid" onSubmit={submit}>
          <div className="field full">
            <label htmlFor="email">Email address</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <div className="field full">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "signup" ? 8 : 1}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={mode === "signup" ? "At least 8 characters" : "Your password"}
            />
          </div>
          {error && <div className="notice error field full">{error}</div>}
          {message && <div className="notice field full">{message}</div>}
          <div className="field full">
            <button className="button" disabled={busy} type="submit">
              {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </div>
        </form>
        <Link className="auth-switch" href={mode === "login" ? "/signup" : "/login"}>
          {mode === "login" ? "New here? Create an account" : "Already registered? Sign in"}
        </Link>
        <Link className="auth-switch" href="/" style={{ color: "var(--muted)", fontWeight: 500 }}>
          Continue without signing in
        </Link>
      </section>
    </main>
  );
}
