import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const apiKey = req.cookies.get("helios_session")?.value;
  return NextResponse.json({ authenticated: Boolean(apiKey) });
}
