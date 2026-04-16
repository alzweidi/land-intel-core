export const appRoles = ['analyst', 'reviewer', 'admin'] as const;

export type AppRole = (typeof appRoles)[number];

export type AuthUser = {
  id: string;
  email: string;
  name: string;
  role: AppRole;
};

export type AuthSession = {
  user: AuthUser;
  issuedAt: string;
  expiresAt: string;
};

export type AuthContext = {
  session: AuthSession | null;
  user: AuthUser | null;
  role: AppRole | null;
  isAuthenticated: boolean;
};

export type AuthCredentials = {
  identifier: string;
  password: string;
};

export type LoginExample = {
  label: string;
  identifier: string;
  password: string;
  role: AppRole;
};

