import { expect, test, type Page } from '@playwright/test';

async function login(page: Page, username: string) {
  await page.goto('/login');
  await page.getByLabel('Nom d’utilisateur').fill(username);
  await page.getByLabel('Mot de passe').fill('demo');
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test('un anonyme est renvoyé vers /login', async ({ page }) => {
  await page.goto('/transactions');
  await expect(page).toHaveURL(/\/login$/);
});

test('ADMIN : accès à Audit, pas à Smart Review', async ({ page }) => {
  await login(page, 'admin1');
  await expect(page.getByText('ESPACE ADMIN')).toBeVisible();
  await page.getByRole('link', { name: 'Audit' }).click();
  await expect(page).toHaveURL(/\/audit$/);
  await page.goto('/reviews');
  await expect(page.getByRole('heading', { name: 'Accès interdit' })).toBeVisible();
});

test('ANALYSTE : accès à Smart Review, pas à Utilisateurs', async ({ page }) => {
  await login(page, 'analyste1');
  await expect(page.getByText('ESPACE ANALYSTE')).toBeVisible();
  await page.getByRole('link', { name: /Smart Review/ }).click();
  await expect(page).toHaveURL(/\/reviews$/);
  await page.goto('/users');
  await expect(page.getByRole('heading', { name: 'Accès interdit' })).toBeVisible();
});
