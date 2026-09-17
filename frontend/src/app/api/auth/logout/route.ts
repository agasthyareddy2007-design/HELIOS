import { NextRequest, NextResponse } from "next/server";
import { sessionStore } from "@/lib/sessionStore";

export async function POST(req: NextRequest) {
  const sessionId = req.cookies.get("helios_session")?.value;
  if (sessionId) {
    sessionStore.delete(sessionId);
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set("helios_session", "", {
    httpOnly: true,
    path: "/",
    maxAge: 0,
  });
  return response;
}
