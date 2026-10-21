import "server-only";

const API_KEY_HEADER = "X-App-API-Key";

function backendConfig() {
  const url = process.env.BACKEND_API_URL?.trim().replace(/\/+$/, "");
  const key = process.env.APP_API_KEY?.trim();
  if (!url || !key || key.length < 32) {
    throw new Error("Set BACKEND_API_URL and a 32-character APP_API_KEY in Vercel.");
  }
  return { url, key };
}

export async function callBackend(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const { url, key } = backendConfig();
  const headers = new Headers(init.headers);
  headers.set(API_KEY_HEADER, key);
  headers.set("Accept", "application/json");
  return fetch(`${url}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    signal: init.signal ?? AbortSignal.timeout(120_000),
  });
}

export function responseMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}
