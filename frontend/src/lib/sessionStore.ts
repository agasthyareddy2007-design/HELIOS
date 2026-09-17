// In-memory session store for API keys.
// Kept in globalThis to survive Hot Module Replacement in Next.js dev server.

const globalAny: any = global;

if (!globalAny.heliosSessionStore) {
  globalAny.heliosSessionStore = new Map<string, string>();
}

export const sessionStore: Map<string, string> = globalAny.heliosSessionStore;
