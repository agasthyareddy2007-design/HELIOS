"use client";

import React, { Component, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ForecastErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("Uncaught error rendering Forecast instrument:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="surface mx-auto max-w-[1500px] overflow-hidden rounded-[1.75rem] p-8 mt-10"
             style={{ boxShadow: "inset 0 0 0 1px rgba(220,38,38,0.2)" }}>
          <div className="flex flex-col items-center justify-center min-h-[300px] text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-red-500/10 mb-4">
              <span className="h-4 w-4 bg-red-400 rounded-full" />
            </span>
            <h2 className="font-display text-xl mb-2 text-white">Rendering Interrupted</h2>
            <p className="font-mono text-sm text-[var(--ink-dim)] mb-6 max-w-[500px]">
              The forecast instrument encountered an unexpected error matching station metadata with live data.
              This typically occurs during rapid location changes.
            </p>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="rounded bg-[var(--helios-amber)] px-6 py-2.5 font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-[#251000] focus:outline-none focus:ring-2 focus:ring-[var(--helios-amber)] focus:ring-offset-2 focus:ring-offset-black"
            >
              Reset Instrument
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
