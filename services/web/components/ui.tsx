import Link from 'next/link';
import type { ReactNode } from 'react';

type BadgeTone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger';

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

export function Badge({
  children,
  tone = 'neutral',
  className
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  return <span className={cx('badge', `badge--${tone}`, className)}>{children}</span>;
}

export function Panel({
  children,
  className,
  eyebrow,
  title,
  note
}: {
  children: ReactNode;
  className?: string;
  eyebrow?: string;
  title: string;
  note?: ReactNode;
}) {
  return (
    <section className={cx('panel', className)}>
      <div className="panel-head">
        <div>
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
  actions
}: {
  eyebrow: string;
  title: string;
  summary: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="page-title">{title}</h1>
        <p className="page-summary">{summary}</p>
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function DefinitionList({
  items
}: {
  items: Array<{
    label: string;
    value: ReactNode;
  }>;
}) {
  return (
    <dl className="definition-grid">
      {items.map((item) => (
        <div className="definition-item" key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
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
