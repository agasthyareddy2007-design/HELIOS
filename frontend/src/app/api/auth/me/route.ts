import { NextRequest, NextResponse } from "next/server";
import { sessionStore } from "@/lib/sessionStore";

export async function GET(req: NextRequest) {
  const sessionId = req.cookies.get("helios_session")?.value;
  const hasValidSession = sessionId ? sessionStore.has(sessionId) : false;
  return NextResponse.json({ authenticated: hasValidSession });
}
