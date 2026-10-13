import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RouterProvider } from 'react-router-dom';
import { AuthProvider } from '@/features/auth/AuthContext';
import { createDemoAuthService } from '@/features/auth/authService';
import { createTestRouter } from './router/routes';

function renderApp(path: string, session?: 'admin1' | 'analyste1') {
  if (session) window.sessionStorage.setItem('frl.demo.session', session);
  const router = createTestRouter([path]);
  render(
    <AuthProvider service={createDemoAuthService(0)}>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
  return router;
}

describe('connexion', () => {
  it('affiche le formulaire et redirige un anonyme depuis /dashboard', async () => {
    renderApp('/dashboard');
    expect(await screen.findByRole('heading', { name: 'Bienvenue' })).toBeInTheDocument();
    expect(screen.getByLabelText('Nom d’utilisateur')).toBeInTheDocument();
    expect(screen.getByLabelText('Mot de passe')).toBeInTheDocument();
  });

  it('signale des identifiants invalides (401) sans changer de page', async () => {
    const user = userEvent.setup();
    const router = renderApp('/login');
    await user.type(await screen.findByLabelText('Nom d’utilisateur'), 'analyste1');
    await user.type(screen.getByLabelText('Mot de passe'), 'mauvais');
    await user.click(screen.getByRole('button', { name: 'Se connecter' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Identifiants invalides');
    expect(router.state.location.pathname).toBe('/login');
  });

  it('exige les deux champs', async () => {
    const user = userEvent.setup();
    renderApp('/login');
    await user.click(await screen.findByRole('button', { name: 'Se connecter' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Renseignez');
  });

  it('connecte un ADMIN et ouvre le dashboard', async () => {
    const user = userEvent.setup();
    const router = renderApp('/login');
    await user.type(await screen.findByLabelText('Nom d’utilisateur'), 'admin1');
    await user.type(screen.getByLabelText('Mot de passe'), 'demo');
    await user.click(screen.getByRole('button', { name: 'Se connecter' }));
    expect(await screen.findByRole('heading', { name: 'Vue d’ensemble' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/dashboard');
  });

  it('bascule la visibilité du mot de passe', async () => {
    const user = userEvent.setup();
    renderApp('/login');
    const input = await screen.findByLabelText('Mot de passe');
    expect(input).toHaveAttribute('type', 'password');
    await user.click(screen.getByRole('button', { name: 'Afficher le mot de passe' }));
    expect(input).toHaveAttribute('type', 'text');
  });
});

describe('sidebar selon le rôle', () => {
  it("ADMIN : Utilisateurs, Audit, Monitoring, Grafana ; pas d'Investigation ni de Smart Review", async () => {
    renderApp('/dashboard', 'admin1');
    const nav = within(await screen.findByRole('navigation', { name: 'Navigation principale' }));
    for (const label of ['Dashboard', 'Clients', 'Transactions', 'Intelligence ML', 'Utilisateurs', 'Audit', 'Notifications', 'Monitoring', 'Grafana', 'Profil']) {
      expect(nav.getByText(label)).toBeInTheDocument();
    }
    expect(nav.queryByText('Investigation')).not.toBeInTheDocument();
    expect(nav.queryByText('Smart Review')).not.toBeInTheDocument();
  });

  it("ANALYSTE : Investigation et Smart Review ; pas d'administration ni de monitoring", async () => {
    renderApp('/dashboard', 'analyste1');
    const nav = within(await screen.findByRole('navigation', { name: 'Navigation principale' }));
    expect(nav.getByText('Investigation')).toBeInTheDocument();
    expect(nav.getByText('Smart Review')).toBeInTheDocument();
    for (const label of ['Utilisateurs', 'Audit', 'Monitoring', 'Grafana']) {
      expect(nav.queryByText(label)).not.toBeInTheDocument();
    }
  });

  it("ouvre /403 quand un ANALYSTE force l'URL /users", async () => {
    renderApp('/users', 'analyste1');
    expect(await screen.findByRole('heading', { name: 'Accès interdit' })).toBeInTheDocument();
  });

  it('la déconnexion renvoie vers /login', async () => {
    const user = userEvent.setup();
    const router = renderApp('/dashboard', 'admin1');
    await user.click(await screen.findByRole('button', { name: /Déconnexion/ }));
    expect(await screen.findByRole('heading', { name: 'Bienvenue' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/login');
  });
});

describe('topbar', () => {
  it('affiche l’espace du rôle et le badge « Données simulées »', async () => {
    renderApp('/dashboard', 'analyste1');
    expect(await screen.findByText('ESPACE ANALYSTE')).toBeInTheDocument();
    expect(screen.getByText('Données simulées')).toBeInTheDocument();
  });

  it('ouvre et ferme le panneau Assistant IA simulé', async () => {
    const user = userEvent.setup();
    renderApp('/dashboard', 'admin1');
    await user.click(await screen.findByRole('button', { name: /Assistant IA/ }));
    expect(screen.getByText(/il ne modifie rien/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Fermer l’assistant' }));
    expect(screen.queryByText(/il ne modifie rien/)).not.toBeInTheDocument();
  });
});
