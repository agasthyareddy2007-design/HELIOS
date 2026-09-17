import { NextRequest, NextResponse } from "next/server";
import { sessionStore } from "@/lib/sessionStore";

/**
 * Server-side proxy to the HELIOS V1 API.
 *
 * The V1 API is protected with `X-API-Key`. This route attaches the key 
 * server-side from an HTTP-Only secure session cookie.
 */
const TIMEOUT_MS = Number(process.env.HELIOS_API_TIMEOUT_MS ?? 15000);
const LIVE_TIMEOUT_MS = Number(process.env.HELIOS_LIVE_TIMEOUT_MS ?? 60000);

async function resolveUpstream(): Promise<string> {
  const envBase = process.env.HELIOS_API_BASE;
  if (!envBase) {
    throw new Error("HELIOS_API_BASE is not defined in environment variables.");
  }
  return envBase.replace(/\/$/, ""); // Strip trailing slash
}

const ALLOWED = new Set([
  "health",
  "models",
  "evaluation",
  "model-arena",
  "samples",
  "forecast",
  "usage",
  "locations",
  "issue-times",
  "resolve",
  "live/status",
  "live/forecast",
]);

export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
) {
  const { path } = await ctx.params;
  const endpoint = path?.join("/") ?? "";

  if (!ALLOWED.has(endpoint)) {
    return NextResponse.json(
      { error: "not_found", message: `Unknown HELIOS endpoint: ${endpoint}` },
      { status: 404 },
    );
  }

  const sessionCookie = req.cookies.get("helios_session")?.value;
  let apiKey = "";
  if (sessionCookie) {
    apiKey = sessionStore.get(sessionCookie) ?? "";
  }

  if (!apiKey && endpoint !== "health") {
    return NextResponse.json({ error: "unauthorized", message: "Valid API key required" }, { status: 401 });
  }

  const search = req.nextUrl.search;
  let upstreamBase: string;
  
  try {
    upstreamBase = await resolveUpstream();
  } catch (err) {
    return NextResponse.json({ error: "api_offline", message: "Failed to resolve backend locator URL." }, { status: 503 });
  }

  const url = `${upstreamBase}/v1/${endpoint}${search}`;
  const budget = endpoint.startsWith("live/") ? LIVE_TIMEOUT_MS : TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), budget);

  const onClientAbort = () => controller.abort();
  if (req.signal.aborted) controller.abort();
  else req.signal.addEventListener("abort", onClientAbort, { once: true });

  try {
    const upstream = await fetch(url, {
      headers: apiKey ? { "X-API-Key": apiKey } : {},
      signal: controller.signal,
      cache: "no-store",
    });

    const text = await upstream.text();
    let body: unknown;
    try {
      body = JSON.parse(text);
    } catch {
      return NextResponse.json({ error: "bad_gateway", message: "HELIOS API returned a non-JSON response." }, { status: 502 });
    }

    return NextResponse.json(body, { status: upstream.status });
  } catch (err) {
    const aborted = err instanceof Error && err.name === "AbortError";
    if (aborted && req.signal.aborted) {
      return NextResponse.json({ error: "client_cancelled" }, { status: 499 });
    }
    return NextResponse.json(
      {
        error: aborted ? "timeout" : "api_offline",
        message: aborted
          ? `HELIOS API did not respond within ${budget} ms.`
          : `Cannot reach the HELIOS API at ${upstreamBase}. Is it running?`,
      },
      { status: aborted ? 504 : 503 },
    );
  } finally {
    clearTimeout(timer);
    req.signal.removeEventListener("abort", onClientAbort);
  }
}
