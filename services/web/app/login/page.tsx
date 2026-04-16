import { redirect } from 'next/navigation';

import { Badge, Panel } from '@/components/ui';
import { getAuthSession, getDefaultLandingPath, getLoginHints } from '@/lib/auth';

export const dynamic = 'force-dynamic';

type SearchParams = Promise<Record<string, string | string[] | undefined>> | Record<string, string | string[] | undefined> | undefined;

function firstValue(value: string | string[] | undefined): string {
  if (Array.isArray(value)) {
    return value[0] ?? '';
  }

  return value ?? '';
}

export default async function LoginPage({ searchParams }: { searchParams?: SearchParams }) {
  const session = await getAuthSession();
  if (session) {
    redirect(getDefaultLandingPath(session.role));
  }

  const params = (await Promise.resolve(searchParams ?? {})) as Record<string, string | string[] | undefined>;
  const nextPath = firstValue(params.next) || '/listings';
  const error = firstValue(params.error);
  const examples = getLoginHints();

  return (
    <div className="login-shell">
      <section className="login-hero">
        <div className="eyebrow">Internal analyst access</div>
        <h1 className="login-title">Sign in to the London land intelligence workspace.</h1>
        <p className="login-summary">
          Local/dev access uses the same role model the product expects in production: analyst,
          reviewer, and admin. Hidden probability stays non-speaking by default unless a scoped
          reviewer/admin context explicitly asks for internal mode.
        </p>
        <div className="login-points">
          <article className="login-point">
            <div className="login-point__label">Protected routes</div>
            <div className="login-point__value">Listings, sites, assessments, opportunities, admin</div>
          </article>
          <article className="login-point">
            <div className="login-point__label">Role-aware UI</div>
            <div className="login-point__value">Reviewer queue and admin controls appear only when allowed</div>
          </article>
          <article className="login-point">
            <div className="login-point__label">Local mode</div>
            <div className="login-point__value">Signed cookie session, no auth bypass in normal flow</div>
          </article>
        </div>
      </section>

      <Panel
        className="login-panel"
        eyebrow="Sign in"
        title="Use a local demo account"
        note={<Badge tone="warning">Hidden-only by default</Badge>}
      >
        {error === 'invalid_credentials' ? (
          <div className="auth-error">The email or password did not match a configured local user.</div>
        ) : null}

        <form action="/api/auth/login" className="login-form" method="post">
          <input name="next" type="hidden" value={nextPath} />

          <label className="field">
            <span>Email</span>
            <input autoComplete="username" autoFocus name="email" placeholder="reviewer@landintel.local" required type="email" />
          </label>

          <label className="field">
            <span>Password</span>
            <input autoComplete="current-password" name="password" placeholder="reviewer-demo" required type="password" />
          </label>

          <div className="login-form__actions">
            <button className="button button--solid login-submit" type="submit">
              Sign in
            </button>
            <Badge tone="neutral">12 hour signed session</Badge>
          </div>
        </form>

        <div className="login-hints">
          <div className="login-hints__title">Local accounts</div>
          <div className="login-hints__grid">
            {examples.map((example) => (
              <article className="login-hint" key={example.role}>
                <Badge
                  tone={
                    example.role === 'admin'
                      ? 'accent'
                      : example.role === 'reviewer'
                        ? 'warning'
                        : 'neutral'
                  }
                >
                  {example.role}
                </Badge>
                <div className="login-hint__name">{example.label}</div>
                <div className="login-hint__value">{example.identifier}</div>
                <div className="login-hint__value">{example.password}</div>
              </article>
            ))}
          </div>
        </div>
      </Panel>
    </div>
  );
}
