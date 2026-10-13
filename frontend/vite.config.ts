/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  css: {
    modules: { localsConvention: 'camelCaseOnly' },
  },
  server: {
    port: 5173,
    // Les futures API passent par la Gateway avec des chemins relatifs /api/v1/...
    // En dev, la cible est configurable ; sans cible, MSW répond.
    proxy: process.env.VITE_DEV_API_TARGET
      ? { '/api/v1': { target: process.env.VITE_DEV_API_TARGET, changeOrigin: true } }
      : undefined,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
