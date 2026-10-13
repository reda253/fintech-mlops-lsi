import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RouterProvider } from 'react-router-dom';
import { createTestRouter } from '@/app/router/routes';
import { AuthProvider } from '@/features/auth/AuthContext';
import { createDemoAuthService } from '@/features/auth/authService';

function renderApp(path: string, session?: 'admin1' | 'analyste1') {
  window.sessionStorage.clear();
  if (session) window.sessionStorage.setItem('frl.demo.session', session);
  const router = createTestRouter([path]);
  render(
    <AuthProvider service={createDemoAuthService(0)}>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
  return router;
}

describe('écran de bienvenue', () => {
  it('« / » ouvre /welcome pour un utilisateur non authentifié', async () => {
    const router = renderApp('/');
    expect(await screen.findByRole('button', { name: 'Accéder à la plateforme' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/welcome');
  });

  it('affiche le PNG original complet, sans texte ajouté', async () => {
    renderApp('/welcome');
    const img = await screen.findByRole('img', { name: /FinTech Risk Intelligence/ });
    expect(img.getAttribute('src')).toContain('00_COMMUN_logo');
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });

  it('ne redirige pas automatiquement : le clic ouvre /login', async () => {
    const user = userEvent.setup();
    const router = renderApp('/welcome');
    await user.click(await screen.findByRole('button', { name: 'Accéder à la plateforme' }));
    expect(router.state.location.pathname).toBe('/login');
    expect(await screen.findByRole('heading', { name: 'Bienvenue' })).toBeInTheDocument();
  });

  it('parcours complet : /welcome → /login → /dashboard (ADMIN)', async () => {
    const user = userEvent.setup();
    const router = renderApp('/');
    await user.click(await screen.findByRole('button', { name: 'Accéder à la plateforme' }));
    await user.type(await screen.findByLabelText('Nom d’utilisateur'), 'admin1');
    await user.type(screen.getByLabelText('Mot de passe'), 'demo');
    await user.click(screen.getByRole('button', { name: 'Se connecter' }));
    expect(await screen.findByRole('heading', { name: 'Vue d’ensemble' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
  });

  it('parcours complet pour un ANALYSTE', async () => {
    const user = userEvent.setup();
    const router = renderApp('/welcome');
    await user.click(await screen.findByRole('button', { name: 'Accéder à la plateforme' }));
    await user.type(await screen.findByLabelText('Nom d’utilisateur'), 'analyste1');
    await user.type(screen.getByLabelText('Mot de passe'), 'demo');
    await user.click(screen.getByRole('button', { name: 'Se connecter' }));
    expect(await screen.findByRole('heading', { name: 'Vue d’ensemble' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
  });

  it('« / » redirige un utilisateur déjà authentifié vers /dashboard', async () => {
    const router = renderApp('/', 'admin1');
    expect(await screen.findByRole('heading', { name: 'Vue d’ensemble' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
  });

  it('une route protégée reste protégée (anonyme → /login)', async () => {
    const router = renderApp('/dashboard');
    expect(await screen.findByRole('heading', { name: 'Bienvenue' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });
});
