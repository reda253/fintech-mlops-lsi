/** Configuration publique lue une seule fois (aucun secret côté frontend). */
export const config = {
  useMocks: (import.meta.env.VITE_USE_MOCKS ?? 'true') === 'true',
  authMode: (import.meta.env.VITE_AUTH_MODE ?? 'demo') as 'demo' | 'jwt',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  grafanaUrl: import.meta.env.VITE_GRAFANA_URL ?? '',
} as const;
