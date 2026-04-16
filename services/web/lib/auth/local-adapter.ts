import type { AuthCredentials, AuthUser, AppRole, LoginExample } from './types';
import { normalizeAuthIdentifier } from './session';

type LocalAccount = {
  id: string;
  name: string;
  email: string;
  role: AppRole;
  password: string;
};

const localAccounts: LocalAccount[] = [
  {
    id: 'local-analyst',
    name: 'Analyst User',
    email: 'analyst@landintel.local',
    role: 'analyst',
    password: 'analyst-demo'
  },
  {
    id: 'local-reviewer',
    name: 'Reviewer User',
    email: 'reviewer@landintel.local',
    role: 'reviewer',
    password: 'reviewer-demo'
  },
  {
    id: 'local-admin',
    name: 'Admin User',
    email: 'admin@landintel.local',
    role: 'admin',
    password: 'admin-demo'
  }
];

function normalizeAccountIdentifier(account: LocalAccount): string[] {
  return [account.email, account.id, account.role].map((value) => normalizeAuthIdentifier(value));
}

export function getLocalAuthExamples(): LoginExample[] {
  return localAccounts.map((account) => ({
    label: account.name,
    identifier: account.email,
    password: account.password,
    role: account.role
  }));
}

export async function authenticateLocalCredentials(credentials: AuthCredentials): Promise<AuthUser | null> {
  const identifier = normalizeAuthIdentifier(credentials.identifier);
  const password = credentials.password.trim();

  if (!identifier || !password) {
    return null;
  }

  const account = localAccounts.find((candidate) =>
    normalizeAccountIdentifier(candidate).includes(identifier)
  );

  if (!account || account.password !== password) {
    return null;
  }

  return {
    id: account.id,
    email: account.email,
    name: account.name,
    role: account.role
  };
}

