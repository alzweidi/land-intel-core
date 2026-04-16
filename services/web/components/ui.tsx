import Link from 'next/link';
import { isValidElement, type ReactNode } from 'react';

export type BadgeTone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger';

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

function formatValue(value: unknown): ReactNode {
  if (isValidElement(value)) {
    return value;
  }

  if (value === null || value === undefined || value === '') {
    return 'Unavailable';
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();

    if (trimmed === '[object Object]') {
      return 'Structured data unavailable.';
    }

    if (
      (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']'))
    ) {
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed && typeof parsed === 'object') {
          return JSON.stringify(parsed, null, 2);
        }
      } catch {
        // Fall through to the raw string below.
      }
    }

    return value;
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value.toLocaleString('en-GB') : 'Unavailable';
  }

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }

  if (value instanceof Date) {
    return value.toLocaleString('en-GB', {
      dateStyle: 'medium',
      timeStyle: 'short'
    });
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return 'None';
    }

    return value
      .map((item, index) => (
        <span key={index}>
          {index > 0 ? ', ' : null}
          {formatValue(item)}
        </span>
      ))
      .reduce<ReactNode>((acc, item) => (acc ? <>{acc}{item}</> : item), null);
  }

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return 'Unavailable';
    }
  }

  return String(value);
}

function statusTone(value: string | null | undefined): BadgeTone {
  const text = (value ?? '').trim().toUpperCase();

  if (!text) {
    return 'neutral';
  }

  if (
    text.includes('PASS') ||
    text.includes('ACTIVE') ||
    text.includes('COMPLETE') ||
    text.includes('READY') ||
    text.includes('CONFIRMED') ||
    text.includes('OPEN')
  ) {
    return 'success';
  }

  if (
    text.includes('FAIL') ||
    text.includes('BLOCK') ||
    text.includes('REJECT') ||
    text.includes('DANGER') ||
    text.includes('ERROR')
  ) {
    return 'danger';
  }

  if (
    text.includes('HOLD') ||
    text.includes('ABSTAIN') ||
    text.includes('REVIEW') ||
    text.includes('WARNING') ||
    text.includes('MANUAL') ||
    text.includes('NOT_READY') ||
    text.includes('INSUFFICIENT')
  ) {
    return 'warning';
  }

  if (text.includes('HIDDEN') || text.includes('RELEASE') || text.includes('REVIEWER')) {
    return 'accent';
  }

  return 'neutral';
}

export function Badge({
  children,
  tone = 'neutral',
  className,
  title
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
  title?: string;
}) {
  return (
    <span className={cx('badge', `badge--${tone}`, className)} title={title}>
      {children}
    </span>
  );
}

export function StatusChip({
  value,
  tone,
  prefix,
  className
}: {
  value: string | null | undefined;
  tone?: BadgeTone;
  prefix?: string;
  className?: string;
}) {
  const resolvedValue = value ?? 'Unavailable';
  return (
    <Badge className={className} tone={tone ?? statusTone(value)}>
      {prefix ? `${prefix} ${resolvedValue}` : resolvedValue}
    </Badge>
  );
}

export function Panel({
  children,
  className,
  eyebrow,
  title,
  note,
  compact = false
}: {
  children: ReactNode;
  className?: string;
  eyebrow?: string;
  title: string;
  note?: ReactNode;
  compact?: boolean;
}) {
  return (
    <section className={cx('panel', compact && 'panel--compact', className)}>
      <div className="panel-head">
        <div className="panel-head__copy">
          {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
          <h2 className="panel-title">{title}</h2>
        </div>
        {note ? <div className="panel-note">{note}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function StatCard({
  label,
  value,
  detail,
  tone = 'neutral'
}: {
  label: string;
  value: string;
  detail: string;
  tone?: BadgeTone;
}) {
  return (
    <article className="stat-card">
      <Badge tone={tone}>{label}</Badge>
      <div className="stat-value">{value}</div>
      <p className="stat-detail">{detail}</p>
    </article>
  );
}

export function PageHeader({
  eyebrow,
  title,
  summary,
  actions,
  badges
}: {
  eyebrow: string;
  title: string;
  summary: string;
  actions?: ReactNode;
  badges?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div className="page-head__copy">
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="page-title">{title}</h1>
        <p className="page-summary">{summary}</p>
        {badges ? <div className="page-badges">{badges}</div> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function DefinitionList({
  items,
  compact = false
}: {
  items: Array<{
    label: string;
    value: unknown;
  }>;
  compact?: boolean;
}) {
  return (
    <dl className={cx('definition-grid', compact && 'definition-grid--compact')}>
      {items.map((item) => (
        <div className="definition-item" key={item.label}>
          <dt>{item.label}</dt>
          <dd className="definition-item__value">{formatValue(item.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SurfaceCard({
  href,
  title,
  summary,
  tag
}: {
  href: string;
  title: string;
  summary: string;
  tag: string;
}) {
  return (
    <Link className="route-card" href={href}>
      <Badge tone="accent">{tag}</Badge>
      <h3>{title}</h3>
      <p>{summary}</p>
      <span className="route-card__footer">Open surface</span>
    </Link>
  );
}

export function MetricGrid({ children }: { children: ReactNode }) {
  return <section className="metric-grid">{children}</section>;
}

export function SectionGrid({
  children,
  className
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={cx('section-grid', className)}>{children}</section>;
}

export function TableShell({
  title,
  note,
  actions,
  children
}: {
  title?: string;
  note?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="table-shell-wrap">
      {(title || note || actions) ? (
        <div className="table-shell-head">
          <div className="table-shell-head__copy">
            {title ? <div className="table-shell-title">{title}</div> : null}
            {note ? <div className="table-shell-note">{note}</div> : null}
          </div>
          {actions ? <div className="table-shell-actions">{actions}</div> : null}
        </div>
      ) : null}
      <div className="table-wrap">{children}</div>
    </section>
  );
}

export function EvidenceList({
  items,
  emptyLabel = 'No evidence available.'
}: {
  items: Array<{
    label: string;
    note: unknown;
    tone?: BadgeTone;
    meta?: ReactNode;
  }>;
  emptyLabel?: string;
}) {
  if (items.length === 0) {
    return <p className="empty-note">{emptyLabel}</p>;
  }

  return (
    <div className="evidence-stack">
      {items.map((item, index) => (
        <article className="evidence-card" key={`${item.label}-${index}`}>
          <div className="evidence-card__head">
            <Badge tone={item.tone ?? 'neutral'}>{item.label}</Badge>
            {item.meta ? <div className="evidence-card__meta">{item.meta}</div> : null}
          </div>
          <p className="evidence-card__note">{formatValue(item.note)}</p>
        </article>
      ))}
    </div>
  );
}

export function ProvenanceList({
  items,
  emptyLabel = 'No provenance available.'
}: {
  items: Array<{
    label: string;
    value: unknown;
    tone?: BadgeTone;
  }>;
  emptyLabel?: string;
}) {
  if (items.length === 0) {
    return <p className="empty-note">{emptyLabel}</p>;
  }

  return (
    <div className="provenance-stack">
      {items.map((item, index) => (
        <div className="provenance-row" key={`${item.label}-${index}`}>
          <div className="provenance-row__copy">
            <div className="provenance-row__label">{item.label}</div>
            <div className="provenance-row__value">{formatValue(item.value)}</div>
          </div>
          <Badge tone={item.tone ?? 'neutral'}>{item.label}</Badge>
        </div>
      ))}
    </div>
  );
}

export function Callout({
  title,
  children,
  tone = 'warning'
}: {
  title: string;
  children: ReactNode;
  tone?: BadgeTone;
}) {
  return (
    <div className={cx('callout', `callout--${tone}`)}>
      <Badge tone={tone}>{title}</Badge>
      <div className="callout__body">{children}</div>
    </div>
  );
}

export function SplitPanel({
  left,
  right,
  className
}: {
  left: ReactNode;
  right: ReactNode;
  className?: string;
}) {
  return <div className={cx('split-layout', className)}>{left}{right}</div>;
}

export function MiniMetric({
  label,
  value,
  tone = 'neutral'
}: {
  label: string;
  value: unknown;
  tone?: BadgeTone;
}) {
  return (
    <article className="mini-metric">
      <Badge tone={tone}>{label}</Badge>
      <div className="mini-metric__value">{formatValue(value)}</div>
    </article>
  );
}
