import { http, HttpResponse } from 'msw';

/**
 * Handlers MSW. Lot 1 : un seul endpoint de santé (l'authentification de démonstration est
 * gérée en mémoire par demoAuthService). Les endpoints /api/v1/... des lots suivants
 * (customers, transactions, risk, ml, notifications, audit) s'ajoutent ici, avec des données
 * déterministes définies dans src/mocks/data/.
 */
export const handlers = [
  http.get('/api/v1/health', () => HttpResponse.json({ status: 'ok', mock: true })),
];
