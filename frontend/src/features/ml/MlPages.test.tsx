import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RouterProvider } from 'react-router-dom';
import { AuthProvider } from '@/features/auth/AuthContext';
import { createDemoAuthService } from '@/features/auth/authService';
import { createTestRouter } from '@/app/router/routes';

function renderMlRoute(path: string, session: 'admin1' | 'analyste1' = 'admin1') {
  window.sessionStorage.setItem('frl.demo.session', session);
  const router = createTestRouter([path]);
  render(
    <AuthProvider service={createDemoAuthService(0)}>
      <RouterProvider router={router} />
    </AuthProvider>,
  );
  return router;
}

describe('Pages Intelligence ML (Issue #50 : §4.11 & §8.4)', () => {
  it('affiche la page Performances ML (/ml) avec le benchmark, la matrice de confusion et la couverture conforme', async () => {
    renderMlRoute('/ml', 'admin1');
    expect(await screen.findByRole('heading', { name: 'Intelligence ML' })).toBeInTheDocument();
    expect(screen.getByText('Benchmark des 5 algorithmes')).toBeInTheDocument();
    expect(screen.getByText('Gradient Boosting (XGBoost)')).toBeInTheDocument();
    expect(screen.getByText('En production')).toBeInTheDocument();
    expect(screen.getByText('Matrice de confusion')).toBeInTheDocument();
    expect(screen.getByText('Incertitude et couverture')).toBeInTheDocument();
    expect(screen.getByText('Couverture visée (1 − α)')).toBeInTheDocument();
    expect(screen.getByText('Validation statistique')).toBeInTheDocument();
  });

  it("affiche la page Visualisations ML (/ml/visualisations) avec l'avertissement obligatoire §4.11 et change de méthode/vue", async () => {
    const user = userEvent.setup();
    renderMlRoute('/ml/visualisations', 'analyste1');
    expect(await screen.findByRole('heading', { name: 'Intelligence ML' })).toBeInTheDocument();
    expect(
      screen.getByText(/seule la proximité locale est interprétable/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Projection t-SNE · vue « uncertainty »/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'UMAP' }));
    await user.click(screen.getByRole('button', { name: 'error' }));
    expect(screen.getByText(/Projection UMAP · vue « error »/i)).toBeInTheDocument();
  });
});
