// In-memory session store for API keys.
// DEPRECATED: Vercel Serverless environments do not persist global state reliably across function instances.
// We will transition to storing the capability token in the HTTP-only cookie directly.

const globalAny: any = global;

if (!globalAny.heliosSessionStore) {
  globalAny.heliosSessionStore = new Map<string, string>();
}

export const sessionStore: Map<string, string> = globalAny.heliosSessionStore;
