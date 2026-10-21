"use client";

import { useEffect, useState } from "react";

type Status = "checking" | "connected" | "not-configured" | "unreachable";

async function check(url: string): Promise<Status> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return "unreachable";
    const body = await response.json();
    if (url.includes("auth/status")) {
      return body.configured ? "connected" : "not-configured";
    }
    return body.status === "ok" ? "connected" : "unreachable";
  } catch {
    return "unreachable";
  }
}

function StatusLabel({ value }: { value: Status }) {
  const text = {
    checking: "Checking connection",
    connected: "Connected",
    "not-configured": "Needs configuration",
    unreachable: "Unavailable",
  }[value];
  const className = value === "connected" ? "status ok" : value === "unreachable" ? "status error" : "status";
  return <span className={className}>{text}</span>;
}

export default function IntegrationStatus() {
  const [api, setApi] = useState<Status>("checking");
  const [supabase, setSupabase] = useState<Status>("checking");
  useEffect(() => {
    void check("/api/backend/health").then(setApi);
    void check("/api/auth/status").then(setSupabase);
  }, []);

  return (
    <div className="integration-list">
      <div className="integration-item">
        <div>
          <h3>FastAPI · Render</h3>
          <p>Backend health and protected API proxy connection.</p>
        </div>
        <StatusLabel value={api} />
      </div>
      <div className="integration-item">
        <div>
          <h3>Supabase · Auth and history</h3>
          <p>Account sign-in and user-owned saved analysis history.</p>
        </div>
        <StatusLabel value={supabase} />
      </div>
      <div className="integration-item">
        <div>
          <h3>Next.js · Vercel</h3>
          <p>The current web interface runs on this Vercel deployment.</p>
        </div>
        <span className="status ok">Frontend active</span>
      </div>
    </div>
  );
}
