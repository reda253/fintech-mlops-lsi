import { expect, test } from '@playwright/test';

test('compiled login renders and demo session survives a reload', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'Bienvenue' })).toBeVisible();
  await expect(page.getByLabel('Nom d\u2019utilisateur')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('login.png'), fullPage: true, animations: 'disabled' });
  await page.getByLabel('Nom d\u2019utilisateur').fill('admin1');
  await page.getByLabel('Mot de passe', { exact: true }).fill('demo');
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Vue d\u2019ensemble' })).toBeVisible();
  const simulated = page.getByText('Donn\u00e9es simul\u00e9es');
  await expect(simulated).toBeAttached();
  if (testInfo.project.name === 'desktop') await expect(simulated).toBeVisible();
  else await expect(simulated).toBeHidden();
  await page.screenshot({ path: testInfo.outputPath('dashboard.png'), fullPage: true, animations: 'disabled' });
  expect(errors).toEqual([]);
});

test('welcome image loads and anonymous deep link redirects to login', async ({ page }, testInfo) => {
  await page.goto('/welcome');
  const logo = page.getByRole('img', { name: /FinTech Risk Intelligence/ });
  await expect(logo).toBeVisible();
  await expect.poll(() => logo.evaluate((element) => Number(Reflect.get(element, 'naturalWidth')))).toBeGreaterThan(0);
  await page.screenshot({ path: testInfo.outputPath('welcome.png'), fullPage: true, animations: 'disabled' });
  await page.goto('/transactions');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Bienvenue' })).toBeVisible();
});
