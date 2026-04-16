'use client';

import { useActionState } from 'react';

import { Badge } from '@/components/ui';
import type { LoginExample } from '@/lib/auth/types';

export type LoginFormState = {
  error: string | null;
  identifier: string;
  nextPath: string;
};

type LoginFormAction = (state: LoginFormState, formData: FormData) => Promise<LoginFormState>;

export function LoginForm({
  action,
  examples,
  nextPath
}: {
  action: LoginFormAction;
  examples: LoginExample[];
  nextPath: string;
}) {
  const [state, formAction, pending] = useActionState(action, {
    error: null,
    identifier: examples[0]?.identifier ?? '',
    nextPath
  });

  return (
    <form className="login-form" action={formAction}>
      <label className="field">
        <span>Email or role</span>
        <input
          autoComplete="username"
          autoFocus
          defaultValue={state.identifier}
          name="identifier"
          placeholder="analyst@landintel.local"
          required
        />
      </label>

      <label className="field">
        <span>Password</span>
        <input
          autoComplete="current-password"
          name="password"
          placeholder="••••••••"
          required
          type="password"
        />
      </label>

      <input name="nextPath" type="hidden" value={state.nextPath} />

      {state.error ? <div className="auth-error">{state.error}</div> : null}

      <div className="login-form__actions">
        <button className="button button--solid login-submit" disabled={pending} type="submit">
          {pending ? 'Signing in…' : 'Sign in'}
        </button>
        <Badge tone="neutral">Secure signed cookie</Badge>
      </div>

      <div className="login-hints">
        <div className="login-hints__title">Local demo accounts</div>
        <div className="login-hints__grid">
          {examples.map((example) => (
            <article className="login-hint" key={example.role}>
              <Badge tone={example.role === 'admin' ? 'accent' : example.role === 'reviewer' ? 'warning' : 'neutral'}>
                {example.role}
              </Badge>
              <div className="login-hint__name">{example.label}</div>
              <div className="login-hint__value">{example.identifier}</div>
              <div className="login-hint__value">{example.password}</div>
            </article>
          ))}
        </div>
      </div>
    </form>
  );
}

