import { NextRequest, NextResponse } from "next/server";
import { sessionStore } from "@/lib/sessionStore";
import crypto from "crypto";

const UPSTREAM = process.env.HELIOS_API_BASE ?? "http://127.0.0.1:8011";
const TIMEOUT_MS = Number(process.env.HELIOS_API_TIMEOUT_MS ?? 15000);

export async function POST(req: NextRequest) {
  try {
    const { apiKey } = await req.json();
    if (!apiKey) {
      return NextResponse.json({ error: "Missing API key" }, { status: 400 });
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

    // Test the key against /v1/locations which requires authentication but reads NO disk state
    const testUrl = `${UPSTREAM}/v1/locations`;
    let res: Response;
    try {
      res = await fetch(testUrl, {
        headers: { "X-API-Key": apiKey },
        signal: controller.signal,
        cache: "no-store",
      });
    } catch {
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

    // Key is valid. Create a session.
    const sessionId = crypto.randomUUID();
    sessionStore.set(sessionId, apiKey);

    const response = NextResponse.json({ ok: true });
    response.cookies.set("helios_session", sessionId, {
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
