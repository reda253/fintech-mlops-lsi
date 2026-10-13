import { ApiError } from '@/api/errors';
import { findDemoAccount, toPublicUser } from '@/mocks/data/demoUsers';
import type { AuthUser, Credentials } from '@/types/auth';

/**
 * Abstraction d'authentification. Le reste de l'application ne dépend que de cette interface.
 *
 * - `demo` (Lot 1) : comptes fictifs en mémoire, AUCUN jeton.
 * - `jwt` (futur) : POST /api/v1/auth/login, /refresh, GET /auth/me. La stratégie de stockage
 *   (access token en mémoire, refresh token en cookie HttpOnly ?) reste à valider avec P1.
 */
export interface AuthService {
  login(credentials: Credentials): Promise<AuthUser>;
  logout(): Promise<void>;
  /** Restaure une session existante au chargement de la page. */
  restore(): Promise<AuthUser | null>;
}

const DEMO_SESSION_KEY = 'frl.demo.session';

/** Latence simulée pour exercer les états de chargement. */
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function createDemoAuthService(latencyMs = 450): AuthService {
  return {
    async login({ username, password }) {
      await delay(latencyMs);
      const account = findDemoAccount(username);
      if (!account || account.password !== password) throw new ApiError(401, 'Identifiants invalides');
      // Seul l'identifiant public est conservé pour survivre à un rechargement (pas de secret).
      window.sessionStorage.setItem(DEMO_SESSION_KEY, account.username);
      return toPublicUser(account);
    },
    async logout() {
      window.sessionStorage.removeItem(DEMO_SESSION_KEY);
    },
    async restore() {
      const username = window.sessionStorage.getItem(DEMO_SESSION_KEY);
      const account = username ? findDemoAccount(username) : undefined;
      return account ? toPublicUser(account) : null;
    },
  };
}

/** Point d'entrée futur : à implémenter une fois la stratégie JWT validée avec P1. */
export function createJwtAuthService(): AuthService {
  const notReady = () => {
    throw new Error("Authentification JWT non implémentée : stratégie à valider avec P1 (backend).");
  };
  return { login: async () => notReady(), logout: async () => notReady(), restore: async () => null };
}
