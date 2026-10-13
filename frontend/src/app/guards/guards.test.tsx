import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { AuthProvider } from '@/features/auth/AuthContext';
import { createDemoAuthService } from '@/features/auth/authService';
import { RequireAuth } from './RequireAuth';
import { RequirePermission } from './RequirePermission';

function renderAt(path: string, loginAs?: 'admin1' | 'analyste1') {
  const service = createDemoAuthService(0);
  if (loginAs) window.sessionStorage.setItem('frl.demo.session', loginAs);
  const router = createMemoryRouter(
    [
      { path: '/login', element: <p>page-login</p> },
      { path: '/403', element: <p>page-403</p> },
      {
        element: <RequireAuth />,
        children: [
          { path: '/dashboard', element: <p>page-dashboard</p> },
          {
            element: <RequirePermission permission="users:manage" />,
            children: [{ path: '/users', element: <p>page-users</p> }],
          },
          {
            element: <RequirePermission permission="reviews:decide" />,
            children: [{ path: '/reviews', element: <p>page-reviews</p> }],
          },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  render(
    <AuthProvider service={service}>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
}

describe('guards', () => {
  it('redirige un anonyme vers /login', async () => {
    renderAt('/dashboard');
    expect(await screen.findByText('page-login')).toBeInTheDocument();
  });

  it('laisse passer un utilisateur connecté', async () => {
    renderAt('/dashboard', 'admin1');
    expect(await screen.findByText('page-dashboard')).toBeInTheDocument();
  });

  it('refuse /users à un ANALYSTE (403)', async () => {
    renderAt('/users', 'analyste1');
    expect(await screen.findByText('page-403')).toBeInTheDocument();
  });

  it("refuse /reviews à l'ADMIN (pas de décision pour l'admin)", async () => {
    renderAt('/reviews', 'admin1');
    expect(await screen.findByText('page-403')).toBeInTheDocument();
  });

  it('autorise /users pour un ADMIN', async () => {
    renderAt('/users', 'admin1');
    expect(await screen.findByText('page-users')).toBeInTheDocument();
  });
});
