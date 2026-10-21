import { NextRequest, NextResponse } from "next/server";
import { callBackend } from "@/lib/backend";

type AuthAction = "login" | "signup" | "logout" | "status";
type AuthPayload = {
  user?: { id?: string; email?: string };
  access_token?: string;
  refresh_token?: string;
  requires_email_confirmation?: boolean;
};

const cookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
};

function clearAuthCookies(response: NextResponse) {
  for (const name of ["auth_access", "auth_refresh", "auth_email"]) {
    response.cookies.set(name, "", { ...cookieOptions, maxAge: 0 });
  }
}

function saveAuthCookies(response: NextResponse, data: AuthPayload) {
  if (data.access_token && data.refresh_token) {
    response.cookies.set("auth_access", data.access_token, {
      ...cookieOptions,
      maxAge: 60 * 60,
    });
    response.cookies.set("auth_refresh", data.refresh_token, {
      ...cookieOptions,
      maxAge: 60 * 60 * 24 * 30,
    });
    response.cookies.set("auth_email", data.user?.email ?? "", {
      ...cookieOptions,
      maxAge: 60 * 60 * 24 * 30,
    });
  }
}

function publicAuthResult(data: AuthPayload) {
  return {
    user: data.user ?? null,
    requires_email_confirmation: Boolean(data.requires_email_confirmation),
  };
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ action: string }> },
) {
  const { action } = await context.params;
  if (!["login", "signup", "logout"].includes(action)) {
    return NextResponse.json({ detail: "Unknown authentication action." }, { status: 404 });
  }

  try {
    let init: RequestInit;
    if (action === "logout") {
      const access = request.cookies.get("auth_access")?.value;
      const refresh = request.cookies.get("auth_refresh")?.value;
      const headers = new Headers();
      if (access) headers.set("Authorization", `Bearer ${access}`);
      if (refresh) headers.set("X-Refresh-Token", refresh);
      init = { method: "POST", headers };
    } else {
      init = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: await request.text(),
      };
    }
    const backendResponse = await callBackend(`/api/auth/${action}`, init);
    let data: AuthPayload & { detail?: string };
    try {
      data = (await backendResponse.json()) as AuthPayload & { detail?: string };
    } catch {
      return NextResponse.json({ detail: "The backend returned an invalid response." }, { status: 502 });
    }
    if (!backendResponse.ok) {
      return NextResponse.json(
        { detail: data.detail ?? "Authentication failed." },
        { status: backendResponse.status },
      );
    }
    const response = NextResponse.json(
      action === "logout" ? { signed_out: true } : publicAuthResult(data),
    );
    if (action === "logout") clearAuthCookies(response);
    else saveAuthCookies(response, data);
    return response;
  } catch (error) {
    const message = error instanceof Error ? error.message : "The API service is unavailable.";
    return NextResponse.json({ detail: message }, { status: 503 });
  }
}

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ action: string }> },
) {
  const { action } = await context.params;
  if (action !== "status") {
    return NextResponse.json({ detail: "Unknown authentication action." }, { status: 404 });
  }
  try {
    const response = await callBackend("/api/auth/status");
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch (error) {
    const message = error instanceof Error ? error.message : "The API service is unavailable.";
    return NextResponse.json({ detail: message }, { status: 503 });
  }
}
