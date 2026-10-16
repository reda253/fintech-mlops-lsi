import { config } from '@/lib/config';
import { ApiError } from './errors';

/**
 * Client HTTP unique. Tous les appels passent par l'API Gateway (chemin relatif /api/v1).
 * Le frontend ne parle jamais directement à PostgreSQL, RabbitMQ ou Kubernetes.
 *
 * Authentification : le jeton (Authorization: Bearer …) sera fourni via `setAuthTokenProvider`
 * lorsque la stratégie JWT sera validée avec P1. Aucun jeton n'est lu depuis localStorage.
 */
type TokenProvider = () => string | null;
let tokenProvider: TokenProvider = () => null;

export function setAuthTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = new URL(`${config.apiBaseUrl}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(opts.query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = tokenProvider();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(url, {
      method: opts.method ?? 'GET',
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch {
    throw new ApiError(0, 'Erreur réseau');
  }

  if (!response.ok) throw new ApiError(response.status);
  return (response.status === 204 ? undefined : await response.json()) as T;
}
