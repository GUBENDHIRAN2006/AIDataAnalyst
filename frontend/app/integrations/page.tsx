import Link from "next/link";
import IntegrationStatus from "@/components/integration-status";

export default function IntegrationsPage() {
  return (
    <div className="shell">
      <header className="topbar">
        <Link className="brand" href="/">
          <img className="brand-image" src="/brand.svg" alt="" /> AI Data Analyst
        </Link>
        <nav className="nav-links">
          <Link className="nav-link" href="/">Workspace</Link>
          <Link className="button-secondary" href="/login"><span className="person-icon">•</span>Account</Link>
        </nav>
      </header>
      <main className="page">
        <div className="eyebrow">Platform connections</div>
        <h1>Integrations</h1>
        <p className="muted">Check the deployed frontend, FastAPI backend, and Supabase account service.</p>
        <section className="card" style={{ marginTop: 22 }}>
          <h2>Connection status</h2>
          <IntegrationStatus />
        </section>
        <section className="grid" style={{ marginTop: 20 }}>
          <article className="card span-4">
            <div className="eyebrow">Frontend</div>
            <h2>Vercel</h2>
            <p className="muted">Deploy the <code>frontend</code> folder as the Vercel project root.</p>
            <p className="small">Set server-only <code>BACKEND_API_URL</code> to the Render service URL and <code>APP_API_KEY</code> to the matching Render secret. Do not add <code>NEXT_PUBLIC_</code> to either value.</p>
          </article>
          <article className="card span-4">
            <div className="eyebrow">API</div>
            <h2>Render</h2>
            <p className="muted">Deploy the FastAPI service from the repository root using <code>render.yaml</code>.</p>
            <p className="small">Configure <code>GROQ_API_KEY</code>, <code>SUPABASE_URL</code>, and <code>SUPABASE_ANON_KEY</code> in Render. Render generates <code>APP_API_KEY</code>.</p>
          </article>
          <article className="card span-4">
            <div className="eyebrow">Accounts and history</div>
            <h2>Supabase</h2>
            <p className="muted">FastAPI uses your Supabase project for email authentication and per-user saved analysis history.</p>
            <p className="small">Run <code>supabase/analysis_history.sql</code> in the Supabase SQL Editor. Keep RLS enabled and use only the anon/publishable key, never the service-role secret.</p>
          </article>
        </section>
        <div className="actions"><Link className="button" href="/">Back to workspace</Link></div>
      </main>
    </div>
  );
}
