import { expect, test } from '@playwright/test';

/**
 * Comparaisons visuelles de non-régression. Première exécution : `npm run e2e:update`
 * pour générer les références. Les maquettes PNG (docs/mockups/) restent la référence humaine ;
 * ces snapshots protègent contre les dérives entre deux commits.
 */
test('login', async ({ page }) => {
  await page.goto('/login');
  await expect(page).toHaveScreenshot('login.png');
});

test('shell ADMIN', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Nom d’utilisateur').fill('admin1');
  await page.getByLabel('Mot de passe').fill('demo');
  await page.getByRole('button', { name: 'Se connecter' }).click();
  await expect(page.getByRole('heading', { name: 'Vue d’ensemble' })).toBeVisible();
  await expect(page).toHaveScreenshot('shell-admin.png');
});
