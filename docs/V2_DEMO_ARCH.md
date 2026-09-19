# HELIOS V2 — Public Demo API Architecture

For the Smart India Hackathon (SIH) jury evaluation, HELIOS currently utilizes a **Same-origin Reverse Proxy Architecture** to provide seamless access for jury members without requiring them to supply API keys.

---

## Architecture Overview

Instead of client-side authentication, all frontend requests run through a Next.js server-side proxy route that injects internal credentials directly to the backend.

- **Client**: Browser makes request to `/api/helios/[...path]`.
- **Proxy**: `/api/helios/[...path]/route.ts` (Next.js server) intercepts the request.
- **Injection**: The Proxy attaches `HELIOS_FRONTEND_API_KEY` (server-side environment variable) to the `X-API-Key` header.
- **Upstream**: Request is forwarded to FastAPI backend at `HELIOS_API_BASE`.

## Security Guardrails

1. **Endpoint Whitelisting**: Only specific read-only public endpoints (`/v1/forecast`, `/v1/live/forecast`, `/v1/locations`, `/v1/health`, etc.) are allowed by the proxy. Mutations and Administrative endpoints (`/v1/admin/*`) are excluded.
2. **Credential Privacy**: The API key is ONLY used within Next.js server actions / route handlers. No API keys or backend credentials are exposed in the client-side JavaScript bundles or DOM.
3. **Cookie Interaction**: While `helios_session` cookies are still technically processed by the backend authenticator (for the original dashboard admin), the public demo flow now acts as an "authenticated-by-default" session via the injected credentials, removing the need for a client-side login screen.

## Deployment Readiness

- No client-side login required: Opening the URL `/forecast` automatically initiates authentication via server-side credentials and renders the forecast instrument.
- Logout removed: The Logout button has been removed from the navigation bar as there is no manual login session to terminate.
- Environment Requirements: Ensure `HELIOS_FRONTEND_API_KEY` is set in the production environment variables.
