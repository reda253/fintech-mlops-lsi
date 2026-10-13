import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import { can, type Permission } from '@/lib/permissions';
import { PATHS } from '../router/paths';

/** Refuse l'accès (équivalent d'un 403) si le rôle courant n'a pas la permission requise. */
export function RequirePermission({ permission }: { permission: Permission }) {
  const { user } = useAuth();
  if (!can(user?.role, permission)) return <Navigate to={PATHS.forbidden} replace />;
  return <Outlet />;
}
