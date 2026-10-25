import { defineConfig, devices } from '@playwright/test';

if (!process.env.FRONTEND_BASE_URL) {
  throw new Error('FRONTEND_BASE_URL must point to the running Docker frontend');
}

export default defineConfig({
  testDir: './tests/docker',
  workers: 1,
  reporter: 'list',
  use: { baseURL: process.env.FRONTEND_BASE_URL, trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], browserName: 'chromium' } },
  ],
});
