import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { humanStatus, statusTone } from "@/lib/fan-data";

/* ---------------------------------------------------------------- Button */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md border font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none",
        size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm",
        variant === "primary" &&
          "border-transparent bg-primary text-primary-foreground hover:bg-primary-hover",
        variant === "secondary" &&
          "border-border-strong bg-card text-foreground hover:bg-secondary",
        variant === "danger" &&
          "border-transparent bg-destructive text-destructive-foreground hover:brightness-110",
        variant === "ghost" &&
          "border-transparent bg-transparent text-muted-foreground hover:bg-secondary hover:text-foreground",
        className,
      )}
      {...props}
    />
  );
}

/* ----------------------------------------------------------------- Badge */

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: "pending" | "success" | "danger" | "neutral" | "accent";
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "num inline-flex items-center rounded-sm px-2 py-0.5 text-2xs font-medium tracking-wide whitespace-nowrap uppercase",
        tone === "pending" && "bg-status-pending text-status-pending-ink",
        tone === "success" && "bg-status-success text-status-success-ink",
        tone === "danger" && "bg-status-danger text-status-danger-ink",
        tone === "accent" && "bg-accent text-accent-foreground",
        tone === "neutral" && "bg-secondary text-muted-foreground",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Never renders a raw backend status string. */
export function StatusBadge({ status }: { status: string | null }) {
  if (status === null) return <Badge tone="neutral">not set</Badge>;
  return <Badge tone={statusTone(status)}>{humanStatus(status)}</Badge>;
}

/** A human always makes the final call in this system — there is no
 * auto-execution path (src/tools/execution.py only ever sets
 * status='executed' via a human approver). `level` is the minimum approver
 * rank required (src/guardrails/policy_gate.py), not whether a human was
 * involved at all, so the label must not claim otherwise. */
export function ApprovalLevelBadge({ level }: { level: "auto" | "manager" | "cfo" }) {
  const label =
    level === "auto"
      ? "any approver"
      : level === "manager"
        ? "manager sign-off"
        : "CFO sign-off";
  return <Badge tone={level === "auto" ? "neutral" : "accent"}>{label}</Badge>;
}

/* --------------------------------------------------------------- Info tip */

/**
 * Hover/focus tooltip. Deliberately CSS-only so the same markup can be
 * rendered by a Jinja2 template with no JavaScript behind it.
 */
export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="relative inline-flex group">
      <span
        aria-label={label}
        className="num inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-border-strong text-[9px] leading-none text-muted-foreground transition-colors hover:border-primary hover:text-primary focus:outline-none focus-visible:border-primary focus-visible:text-primary"
      >
        ?
      </span>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 w-60 -translate-x-1/2 rounded-md border border-border-strong bg-sidebar px-3 py-2 text-2xs leading-relaxed text-sidebar-foreground opacity-0 shadow-lg transition-opacity duration-100 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {children}
      </span>
    </span>
  );
}

/* ------------------------------------------------------------- Risk scale */

export function riskBand(score: number) {
  if (score >= 0.7)
    return { tone: "danger" as const, word: "high risk", color: "var(--color-status-danger-ink)" };
  if (score >= 0.4)
    return {
      tone: "pending" as const,
      word: "middling risk",
      color: "var(--color-status-pending-ink)",
    };
  return { tone: "success" as const, word: "low risk", color: "var(--color-status-success-ink)" };
}

const RISK_EXPLAINER =
  "Risk runs 0.00 to 1.00, where 0.00 is safest and 1.00 is riskiest. Below 0.40 the pipeline can approve on its own, 0.40–0.69 needs a person, 0.70 and above is where it usually declines unless you override it.";

/** Never renders the bare float — the 0.00–1.00 scale is always next to it. */
export function RiskMeter({ score, compact }: { score: number | null; compact?: boolean }) {
  if (score === null) {
    return compact ? (
      <span className="text-2xs text-muted-foreground">not yet scored</span>
    ) : (
      <div className="w-full max-w-md">
        <span className="text-sm text-muted-foreground">
          Not yet scored — this request reached the queue before the risk agent ran.
        </span>
      </div>
    );
  }

  const band = riskBand(score);

  if (compact) {
    return (
      <div className="flex items-center gap-2" title={`${score.toFixed(2)} of 1.00 — ${band.word}`}>
        <span className="num text-xs font-semibold tabular-nums">{score.toFixed(2)}</span>
        <div
          className="relative h-1 w-16 rounded-full bg-secondary"
          role="img"
          aria-label={`Risk ${score.toFixed(2)} out of 1.00, where 0.00 is safest — ${band.word}`}
        >
          <div
            className="h-full rounded-full"
            style={{ width: `${Math.round(score * 100)}%`, background: band.color }}
          />
        </div>
        <span className="text-2xs whitespace-nowrap text-muted-foreground">
          of 1.00 · {band.word}
        </span>
      </div>
    );
  }

  return (
    <div className="w-full max-w-md">
      <div className="flex items-end justify-between gap-3">
        <div className="flex items-baseline gap-2">
          <span className="num text-2xl font-semibold tabular-nums" style={{ color: band.color }}>
            {score.toFixed(2)}
          </span>
          <span className="text-xs text-muted-foreground">
            on a 0.00–1.00 risk scale (0.00 safest, 1.00 riskiest)
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Badge tone={band.tone}>{band.word}</Badge>
          <InfoTip label="How the risk scale works">{RISK_EXPLAINER}</InfoTip>
        </div>
      </div>

      <div
        className="relative mt-3 h-2 rounded-full bg-secondary"
        role="img"
        aria-label={`Risk ${score.toFixed(2)} out of 1.00, where 0.00 is safest — ${band.word}`}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.round(score * 100)}%`, background: band.color }}
        />
        {[0.4, 0.7].map((t) => (
          <span
            key={t}
            aria-hidden
            className="absolute top-[-3px] h-[14px] w-px bg-border-strong"
            style={{ left: `${t * 100}%` }}
          />
        ))}
        <span
          aria-hidden
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card shadow"
          style={{ left: `${Math.round(score * 100)}%`, background: band.color }}
        />
      </div>

      <div className="num mt-1.5 flex justify-between text-2xs text-muted-foreground">
        <span>0.00 safest</span>
        <span>0.40 human</span>
        <span>0.70 decline</span>
        <span>1.00 riskiest</span>
      </div>
    </div>
  );
}


/* ------------------------------------------------------------ Page header */

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
      <div className="max-w-2xl">
        {eyebrow ? <p className="label-mono mb-2">{eyebrow}</p> : null}
        <h1 className="text-2xl font-semibold">{title}</h1>
        {description ? (
          <p className="mt-2 text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/* ------------------------------------------------------------ Stat / card */

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "accent";
}) {
  return (
    <div className="surface p-4">
      <p className="label-mono">{label}</p>
      <p
        className={cn(
          "num mt-2 text-xl font-semibold",
          tone === "accent" && "text-primary",
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-2xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function Panel({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("surface overflow-hidden", className)}>
      {title ? (
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold">{title}</h2>
            {description ? (
              <p className="mt-1 text-xs text-muted-foreground">{description}</p>
            ) : null}
          </div>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/* --------------------------------------------------- Empty / loading state */

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div
        aria-hidden
        className="mb-4 h-8 w-8 rounded-sm border border-dashed border-border-strong"
      />
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1.5 max-w-sm text-xs text-muted-foreground">{body}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-5" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-bar h-5" style={{ width: `${95 - i * 7}%` }} />
      ))}
    </div>
  );
}

/* ----------------------------------------------------------------- Table */

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  );
}

export function Th({
  children,
  align = "left",
}: {
  children: ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      scope="col"
      className={cn(
        "label-mono border-b border-border bg-secondary/60 px-4 py-2.5 font-medium",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  mono,
  className,
}: {
  children: ReactNode;
  align?: "left" | "right";
  mono?: boolean;
  className?: string;
}) {
  return (
    <td
      className={cn(
        "border-b border-border px-4 py-3 align-middle",
        align === "right" ? "text-right" : "text-left",
        mono && "num",
        className,
      )}
    >
      {children}
    </td>
  );
}

/* ----------------------------------------------------------------- Field */

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="label-mono mb-1.5 block">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-2xs text-muted-foreground">{hint}</span> : null}
    </label>
  );
}

export const inputClass =
  "h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground transition-colors hover:border-border-strong focus:border-ring disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60";

/* --------------------------------------------------------------- Toolbar */

export function Toolbar({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end gap-3 border-b border-border bg-secondary/40 px-5 py-3">
      {children}
    </div>
  );
}

export function SearchInput({
  value,
  onChange,
  placeholder,
  label = "Search",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  label?: string;
}) {
  return (
    <label className="min-w-[200px] flex-1">
      <span className="label-mono mb-1 block">{label}</span>
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(inputClass, "h-9")}
      />
    </label>
  );
}

export function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="min-w-[150px]">
      <span className="label-mono mb-1 block">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(inputClass, "h-9 pr-8")}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Clickable column header. Plain button so a form/link version ports cleanly. */
export function SortTh({
  children,
  align = "left",
  active,
  direction,
  onClick,
}: {
  children: ReactNode;
  align?: "left" | "right";
  active: boolean;
  direction: "asc" | "desc";
  onClick: () => void;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "label-mono border-b border-border bg-secondary/60 px-4 py-2.5 font-medium",
        align === "right" ? "text-right" : "text-left",
      )}
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "inline-flex items-center gap-1 transition-colors hover:text-foreground focus:outline-none focus-visible:text-primary",
          active ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {children}
        <span aria-hidden className="text-[9px]">
          {active ? (direction === "asc" ? "▲" : "▼") : "↕"}
        </span>
      </button>
    </th>
  );
}

/* ----------------------------------------------------------------- Meter */

export function ShareBar({
  value,
  tone = "accent",
}: {
  value: number;
  tone?: "accent" | "success" | "danger";
}) {
  const color =
    tone === "success"
      ? "var(--color-status-success-ink)"
      : tone === "danger"
        ? "var(--color-status-danger-ink)"
        : "var(--color-primary)";
  return (
    <div className="h-1.5 w-full rounded-full bg-secondary" aria-hidden>
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: color }}
      />
    </div>
  );
}
