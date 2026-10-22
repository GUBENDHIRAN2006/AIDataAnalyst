import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { callBackend } from "@/lib/backend";

const allowedRoutes = new Set([
  "health",
  "api/auth/status",
  "api/auth/me",
  "api/history",
  "api/database/tables",
  "api/database/import",
  "api/analyze",
]);
const BODY_LIMIT = 3_500_000;
export const maxDuration = 60;

function copyRotatedSession(response: NextResponse, body: Record<string, unknown>) {
  const access = body.access_token;
  const refresh = body.refresh_token;
  delete body.access_token;
  delete body.refresh_token;
  if (typeof access === "string" && access && typeof refresh === "string" && refresh) {
    const secure = process.env.NODE_ENV === "production";
    response.cookies.set("auth_access", access, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60,
    });
    response.cookies.set("auth_refresh", refresh, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
  }
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path: segments } = await context.params;
  const path = segments.join("/");
  if (!allowedRoutes.has(path)) {
    return NextResponse.json({ detail: "This backend route is not available." }, { status: 404 });
  }
  const method = request.method;
  if (path === "health" && method !== "GET") {
    return NextResponse.json({ detail: "Method not allowed." }, { status: 405 });
  }
  if (path !== "health" && method !== "GET" && method !== "POST") {
    return NextResponse.json({ detail: "Method not allowed." }, { status: 405 });
  }

  try {
    const jar = await cookies();
    const headers = new Headers();
    const access = jar.get("auth_access")?.value;
    const refresh = jar.get("auth_refresh")?.value;
    if (access) headers.set("Authorization", `Bearer ${access}`);
    if (refresh) headers.set("X-Refresh-Token", refresh);
    let body: string | undefined;
    if (method === "POST") {
      body = await request.text();
      if (new TextEncoder().encode(body).byteLength > BODY_LIMIT) {
        return NextResponse.json(
          { detail: "This Vercel endpoint accepts data up to 3.5 MB. Select a smaller dataset." },
          { status: 413 },
        );
      }
      headers.set("Content-Type", request.headers.get("content-type") ?? "application/json");
    }
    const backendResponse = await callBackend(
      path === "health" ? "/health" : `/${path}`,
      { method, headers, body },
    );
    let payload: unknown;
    try {
      payload = await backendResponse.json();
    } catch {
      return NextResponse.json({ detail: "The backend returned an invalid response." }, { status: 502 });
    }
    const response = NextResponse.json(payload, { status: backendResponse.status });
    if (payload && typeof payload === "object") {
      copyRotatedSession(response, payload as Record<string, unknown>);
    }
    return response;
  } catch (error) {
    const message = error instanceof Error ? error.message : "The API service is unavailable.";
    return NextResponse.json({ detail: message }, { status: 503 });
  }
}

export const GET = proxy;
export const POST = proxy;
