import type { AuthUser } from '@/types/auth';

/**
 * COMPTES DE DÉMONSTRATION — aucune valeur réelle, aucun JWT.
 * Utilisés uniquement par `demoAuthService` (VITE_AUTH_MODE=demo).
 */
interface DemoAccount extends AuthUser {
  password: string;
}

export const DEMO_ACCOUNTS: readonly DemoAccount[] = [
  { username: 'admin1', password: 'demo', displayName: 'Administrateur démo', initials: 'NE', role: 'ADMIN' },
  { username: 'analyste1', password: 'demo', displayName: 'Analyste démo', initials: 'YB', role: 'ANALYSTE' },
];

export function findDemoAccount(username: string): DemoAccount | undefined {
  return DEMO_ACCOUNTS.find((a) => a.username === username.trim().toLowerCase());
}

export function toPublicUser(account: DemoAccount): AuthUser {
  const { username, displayName, initials, role } = account;
  return { username, displayName, initials, role };
}
