"use client";

import Link from "next/link";
import { useCallback, useRef, type ReactNode } from "react";
import clsx from "clsx";

/**
 * HELIOS control surface.
 *
 * One interaction language for every actionable element on the site. The
 * material is the same optical vocabulary as `.surface`: translucent body, fine
 * border, internal top highlight, restrained shadow. Interaction is physical
 * rather than decorative:
 *
 *   rest      settled material
 *   hover     a local radial light follows the pointer across the surface
 *   active    presses in (scale + reduced highlight) — a real button travel
 *   focus     a visible amber ring for keyboard users (never removed)
 *   disabled  material flattens, pointer events off, aria-disabled set
 *
 * The pointer highlight is written straight to CSS custom properties on the
 * element, so hovering never triggers a React render. Touch devices and
 * reduced-motion users simply never get the moving highlight.
 */

export type ButtonVariant = "primary" | "secondary" | "ghost";
export type ButtonSize = "md" | "lg";

export interface ButtonProps {
  children: ReactNode;
  /** Render as a Next link when provided. */
  href?: string;
  onClick?: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  className?: string;
  type?: "button" | "submit";
  ariaLabel?: string;
  /** Trailing affordance, e.g. an arrow. */
  trailing?: ReactNode;
}

const SIZES: Record<ButtonSize, string> = {
  // min-height keeps every control at/above a 44px touch target
  md: "min-h-[44px] px-5 py-2.5 text-[12px]",
  lg: "min-h-[52px] px-7 py-3.5 text-[13px]",
};

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "text-[#170f02] bg-[var(--helios-amber)] border border-[color-mix(in_srgb,var(--helios-amber)_70%,white)] " +
    "shadow-[inset_0_1px_0_rgba(255,255,255,0.45),0_18px_40px_-22px_rgba(255,199,115,0.55)] " +
    "hover:brightness-[1.06]",
  secondary:
    "text-[var(--ink)] surface " +
    "hover:border-[rgba(150,190,240,0.26)]",
  ghost:
    "text-[var(--ink-dim)] border border-transparent " +
    "hover:text-[var(--ink)] hover:border-[rgba(126,165,218,0.18)]",
};

export function Button({
  children,
  href,
  onClick,
  variant = "primary",
  size = "md",
  disabled,
  className,
  type = "button",
  ariaLabel,
  trailing,
}: ButtonProps) {
  const ref = useRef<HTMLElement | null>(null);

  // Pointer-tracked local light. Written to CSS vars — no React state.
  const onMove = useCallback((e: React.PointerEvent) => {
    if (e.pointerType === "touch") return;
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${((e.clientX - r.left) / r.width) * 100}%`);
    el.style.setProperty("--my", `${((e.clientY - r.top) / r.height) * 100}%`);
  }, []);

  const onLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--mx", "50%");
    el.style.setProperty("--my", "50%");
  }, []);

  const cls = clsx(
    "helios-control group relative inline-flex select-none items-center justify-center gap-2.5 overflow-hidden",
    "rounded-full font-mono uppercase tracking-[0.16em]",
    "transition-[transform,filter,border-color,color,background-color] duration-200 ease-out",
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]",
    "active:scale-[0.985]",
    SIZES[size],
    VARIANTS[variant],
    disabled && "pointer-events-none opacity-45 shadow-none saturate-50",
    className,
  );

  const inner = (
    <>
      {/* local light field — purely CSS, driven by --mx/--my */}
      <span aria-hidden className="helios-control__light" />
      <span className="relative z-[1]">{children}</span>
      {trailing && (
        <span
          aria-hidden
          className="relative z-[1] transition-transform duration-200 group-hover:translate-x-0.5"
        >
          {trailing}
        </span>
      )}
    </>
  );

  if (href && !disabled) {
    return (
      <Link
        ref={ref as React.Ref<HTMLAnchorElement>}
        href={href}
        aria-label={ariaLabel}
        className={cls}
        onPointerMove={onMove}
        onPointerLeave={onLeave}
      >
        {inner}
      </Link>
    );
  }

  return (
    <button
      ref={ref as React.Ref<HTMLButtonElement>}
      type={type}
      onClick={onClick}
      disabled={disabled}
      aria-disabled={disabled || undefined}
      aria-label={ariaLabel}
      className={cls}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
    >
      {inner}
    </button>
  );
}

export default Button;
