"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";

interface AuthGateProps {
  onAuthenticated: () => void;
  show: boolean;
}

export function AuthGate({ onAuthenticated, show }: AuthGateProps) {
  const [key, setKey] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!key.trim()) return;
    setStatus("loading");
    
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: key.trim() }),
      });
      
      if (res.ok) {
        setStatus("idle");
        onAuthenticated();
      } else {
        setStatus("error");
        const body = await res.json().catch(() => ({}));
        setErrorMsg(body.error || "Invalid API key");
      }
    } catch {
      setStatus("error");
      setErrorMsg("Network error");
    }
  };

  if (!show) return null;

  return (
    <AnimatePresence>
      <motion.div
        key="auth-gate"
        className="fixed left-0 top-0 z-[150] flex h-[100dvh] w-screen flex-col items-center justify-center bg-black/80 backdrop-blur-md"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.6 }}
      >
        <div className="flex w-full max-w-md flex-col gap-6 p-8">
          <div className="flex flex-col gap-2 text-center">
            <h1 className="font-display text-2xl font-light text-white tracking-wide">
              Authentication Required
            </h1>
            <p className="text-[var(--ink-dim)] font-mono text-xs uppercase tracking-[0.1em]">
              Enter your HELIOS API Key
            </p>
          </div>

          <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <input
                type="password"
                value={key}
                onChange={(e) => {
                  setKey(e.target.value);
                  if (status === "error") setStatus("idle");
                }}
                placeholder="hl_demo_..."
                className="w-full rounded-md border border-white/10 bg-black/40 px-4 py-3 font-mono text-sm text-[var(--helios-amber)] outline-none transition-colors focus:border-[var(--helios-amber)]/50 focus:bg-black/60 focus:ring-1 focus:ring-[var(--helios-amber)]/50 placeholder:text-white/20"
                disabled={status === "loading"}
                autoFocus
              />
              {status === "error" && (
                <p className="font-mono text-[11px] text-[var(--color-warn)] uppercase tracking-wider">
                  {errorMsg}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={status === "loading" || !key.trim()}
              className="group relative flex w-full items-center justify-center overflow-hidden rounded-md bg-[var(--helios-amber)] px-4 py-3 font-mono text-[12px] font-semibold uppercase tracking-[0.15em] text-black transition-all hover:bg-[var(--helios-amber)]/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="relative z-10">{status === "loading" ? "Validating..." : "Continue"}</span>
            </button>
          </form>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
