import { Navigate } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import { PATHS } from '../router/paths';

/** Route « / » : anonyme → /welcome ; session ouverte → /dashboard (comportement existant). */
export function RootRedirect() {
  const { status } = useAuth();
  if (status === 'loading') {
    return (
      <div role="status" aria-live="polite" style={{ minHeight: '100%', display: 'grid', placeItems: 'center' }}>
        <span className="sr-only">Chargement de la session…</span>
      </div>
    );
  }
  return <Navigate to={status === 'authenticated' ? PATHS.dashboard : PATHS.welcome} replace />;
}
