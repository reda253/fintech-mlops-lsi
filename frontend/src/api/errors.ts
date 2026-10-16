/** Erreur HTTP normalisée : permet à l'UI de réagir à 401/403/404/409/5xx de façon uniforme. */
export type ApiErrorKind =
  | 'validation' // 400
  | 'unauthenticated' // 401
  | 'forbidden' // 403
  | 'not_found' // 404
  | 'conflict' // 409
  | 'rate_limited' // 429
  | 'server' // 5xx
  | 'unavailable' // 503
  | 'network'
  | 'unknown';

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;

  constructor(status: number, message?: string) {
    super(message ?? `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.kind = ApiError.kindOf(status);
  }

  static kindOf(status: number): ApiErrorKind {
    if (status === 0) return 'network';
    if (status === 400) return 'validation';
    if (status === 401) return 'unauthenticated';
    if (status === 403) return 'forbidden';
    if (status === 404) return 'not_found';
    if (status === 409) return 'conflict';
    if (status === 429) return 'rate_limited';
    if (status === 503) return 'unavailable';
    if (status >= 500) return 'server';
    return 'unknown';
  }
}
