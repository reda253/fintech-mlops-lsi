import type { IconName } from '@/components/ui/Icon';
import type { Permission } from '@/lib/permissions';
import type { Role } from '@/types/auth';
import { PATHS } from './router/paths';

export type CounterKey = 'openReviews' | 'unreadNotifications';

export interface NavItem {
  label: string;
  to: string;
  icon: IconName;
  /** Absent = accessible à tout utilisateur connecté. */
  permission?: Permission;
  counter?: CounterKey;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

/** Navigation par rôle, telle qu'elle apparaît dans les maquettes 02 (ADMIN) et 03 (ANALYSTE). */
const NAV: Record<Role, NavSection[]> = {
  ADMIN: [
    {
      title: 'Général',
      items: [
        { label: 'Dashboard', to: PATHS.dashboard, icon: 'dashboard', permission: 'transactions:read' },
        { label: 'Clients', to: PATHS.clients, icon: 'users', permission: 'customers:read' },
        { label: 'Transactions', to: PATHS.transactions, icon: 'transactions', permission: 'transactions:read' },
        { label: 'Intelligence ML', to: PATHS.ml, icon: 'chart', permission: 'ml:read' },
      ],
    },
    {
      title: 'Administration',
      items: [
        { label: 'Utilisateurs', to: PATHS.users, icon: 'user', permission: 'users:manage' },
        { label: 'Audit', to: PATHS.audit, icon: 'file', permission: 'audit:read' },
        {
          label: 'Notifications',
          to: PATHS.notifications,
          icon: 'bell',
          permission: 'notifications:read',
          counter: 'unreadNotifications',
        },
      ],
    },
    {
      title: 'Observabilité',
      items: [
        { label: 'Monitoring', to: PATHS.monitoring, icon: 'activity', permission: 'monitoring:read' },
        { label: 'Grafana', to: PATHS.grafana, icon: 'trend', permission: 'monitoring:read' },
      ],
    },
  ],
  ANALYSTE: [
    {
      title: 'Général',
      items: [
        { label: 'Dashboard', to: PATHS.dashboard, icon: 'dashboard', permission: 'transactions:read' },
        { label: 'Investigation', to: PATHS.investigation, icon: 'sparkle', permission: 'reviews:read' },
        { label: 'Smart Review', to: PATHS.reviews, icon: 'list', permission: 'reviews:read', counter: 'openReviews' },
        { label: 'Transactions', to: PATHS.transactions, icon: 'transactions', permission: 'transactions:read' },
        { label: 'Clients', to: PATHS.clients, icon: 'users', permission: 'customers:read' },
        { label: 'Intelligence ML', to: PATHS.ml, icon: 'chart', permission: 'ml:read' },
      ],
    },
    {
      title: 'Alertes',
      items: [
        {
          label: 'Notifications',
          to: PATHS.notifications,
          icon: 'bell',
          permission: 'notifications:read',
          counter: 'unreadNotifications',
        },
      ],
    },
  ],
};

/** Section « Autre » commune aux deux rôles (Profil ; la déconnexion est une action). */
export const OTHER_ITEMS: NavItem[] = [
  { label: 'Profil', to: PATHS.profile, icon: 'user' },
];

export function navigationFor(role: Role): NavSection[] {
  return NAV[role];
}

/** Libellés du fil d'Ariane : [parent, enfant]. */
const CRUMBS: Array<{ match: RegExp; trail: [string, string] }> = [
  { match: /^\/dashboard/, trail: ['Dashboard', "Vue d’ensemble"] },
  { match: /^\/clients\/new/, trail: ['Clients', 'Nouveau client'] },
  { match: /^\/clients\/[^/]+\/edit/, trail: ['Clients', 'Modifier'] },
  { match: /^\/clients\/[^/]+/, trail: ['Clients', 'Fiche client'] },
  { match: /^\/clients/, trail: ['Clients', 'Liste'] },
  { match: /^\/transactions/, trail: ['Transactions', 'Liste'] },
  { match: /^\/investigation/, trail: ['Investigation', 'Espace de travail'] },
  { match: /^\/reviews\/[^/]+/, trail: ['Smart Review', 'Dossier'] },
  { match: /^\/reviews/, trail: ['Smart Review', 'File de revue'] },
  { match: /^\/ml\/visualisations/, trail: ['Intelligence ML', 'Visualisations'] },
  { match: /^\/ml/, trail: ['Intelligence ML', 'Performances'] },
  { match: /^\/notifications/, trail: ['Notifications', 'Toutes'] },
  { match: /^\/users/, trail: ['Administration', 'Utilisateurs'] },
  { match: /^\/audit/, trail: ['Administration', 'Audit'] },
  { match: /^\/monitoring/, trail: ['Observabilité', 'Monitoring'] },
  { match: /^\/grafana/, trail: ['Observabilité', 'Grafana'] },
  { match: /^\/profile/, trail: ['Autre', 'Profil'] },
];

export function breadcrumbFor(pathname: string): [string, string] {
  return CRUMBS.find((c) => c.match.test(pathname))?.trail ?? ['Dashboard', "Vue d’ensemble"];
}
