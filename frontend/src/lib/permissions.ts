import type { Role } from '@/types/auth';

/**
 * Matrice des droits (maquettes_conformite.md §5).
 * L'UI masque les actions interdites ; l'autorisation réelle reste imposée par le backend.
 */
export type Permission =
  | 'customers:read'
  | 'customers:write'
  | 'transactions:read'
  | 'risk:read'
  | 'reviews:read'
  | 'reviews:decide'
  | 'ml:read'
  | 'notifications:read'
  | 'users:manage'
  | 'audit:read'
  | 'monitoring:read';

const COMMON: Permission[] = [
  'customers:read',
  'transactions:read',
  'risk:read',
  'ml:read',
  'notifications:read',
];

const ROLE_PERMISSIONS: Record<Role, ReadonlySet<Permission>> = {
  ADMIN: new Set<Permission>([...COMMON, 'customers:write', 'users:manage', 'audit:read', 'monitoring:read']),
  ANALYSTE: new Set<Permission>([...COMMON, 'reviews:read', 'reviews:decide']),
};

export function can(role: Role | undefined, permission: Permission): boolean {
  return role ? ROLE_PERMISSIONS[role].has(permission) : false;
}
