import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import { PATHS } from '../router/paths';

/** Redirige vers /login si aucune session (équivalent d'un 401), en mémorisant la destination. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return (
      <div role="status" aria-live="polite" style={{ minHeight: '100%', display: 'grid', placeItems: 'center' }}>
        <span className="sr-only">Chargement de la session…</span>
      </div>
    );
  }
  if (status === 'anonymous') {
    return <Navigate to={PATHS.login} replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}
