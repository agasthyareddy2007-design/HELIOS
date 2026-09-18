import { NextRequest, NextResponse } from "next/server";

const TIMEOUT_MS = Number(process.env.HELIOS_API_TIMEOUT_MS ?? 15000);

async function resolveUpstream(): Promise<string> {
  const envBase = process.env.HELIOS_API_BASE;
  if (!envBase) {
    // Fallback to local dev for robustness if env is missing
    return "http://127.0.0.1:8011";
  }
  return envBase.replace(/\/$/, ""); // Strip trailing slash
}

export async function POST(req: NextRequest) {
  try {
    const { apiKey } = await req.json();
    if (!apiKey) {
      return NextResponse.json({ error: "Missing API key" }, { status: 400 });
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

    // Test the key against /v1/usage which is extremely lightweight (45 bytes)
    // and requires authentication but implies NO database scans.
    let testUrl: string;
    try {
      const upstreamBase = await resolveUpstream();
      testUrl = `${upstreamBase}/v1/usage`;
    } catch {
      return NextResponse.json({ error: "Backend unconfigured" }, { status: 503 });
    }

    let res: Response;
    try {
      res = await fetch(testUrl, {
        headers: { "X-API-Key": apiKey },
        signal: controller.signal,
        cache: "no-store",
      });
      // CRITICAL VERCEL SERVERLESS FIX:
      // We must explicitly consume the body (`res.text()`) even if we don't need it.
      // Failing to consume the body in Node.js 18+ (undici) leaves the TCP connection
      // in a hanging state, leading to BrokenPipeErrors on the backend and 502/connection
      // pool exhaustion bugs on Vercel on subsequent validation attempts.
      await res.text().catch(() => "");
    } catch (err) {
      // Safely ignore aborts from client or genuine network errors
      return NextResponse.json({ error: "Backend unreachable" }, { status: 502 });
    } finally {
      clearTimeout(timer);
    }

    if (res.status === 401 || res.status === 403) {
      return NextResponse.json({ error: "Invalid API key" }, { status: 401 });
    }
    
    if (!res.ok) {
       return NextResponse.json({ error: "Backend error during validation" }, { status: 502 });
    }

    // Vercel Serverless Fix: Store the valid API key directly in the HTTP-only cookie.
    // In-memory Maps (sessionStore) reset across Edge/Serverless function invocations.
    const response = NextResponse.json({ ok: true });
    response.cookies.set("helios_session", apiKey, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 43200, // 12 hours
      path: "/",
    });
    return response;
  } catch (err) {
    return NextResponse.json({ error: "Validation failed" }, { status: 500 });
  }
}
