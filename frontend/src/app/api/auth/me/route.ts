import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  // Public Demo mode: By default, the application is open and authenticated
  // using the server-side HELIOS_FRONTEND_API_KEY for allowlisted endpoints.
  // We inform the frontend that it is authenticated so it bypassing the login wall.
  const hasServerKey = Boolean(process.env.HELIOS_FRONTEND_API_KEY || process.env.HELIOS_API_KEY);
  const sessionApiKey = req.cookies.get("helios_session")?.value;

  return NextResponse.json({ authenticated: hasServerKey || Boolean(sessionApiKey) });
}
