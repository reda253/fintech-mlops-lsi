/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCKS: string;
  readonly VITE_AUTH_MODE: 'demo' | 'jwt';
  readonly VITE_API_BASE_URL: string;
  readonly VITE_GRAFANA_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
