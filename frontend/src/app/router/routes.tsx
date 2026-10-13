import { createBrowserRouter, createMemoryRouter, type RouteObject } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { LoginPage } from '@/features/auth/LoginPage';
import { WelcomePage } from '@/features/welcome/WelcomePage';
import { PlaceholderPage } from '@/features/placeholder/PlaceholderPage';
import { ForbiddenPage, NotFoundPage } from '@/features/placeholder/StatusPages';
import { RequireAuth } from '../guards/RequireAuth';
import { RootRedirect } from '../guards/RootRedirect';
import { RequirePermission } from '../guards/RequirePermission';
import { PATHS } from './paths';

/**
 * Table de routage centralisée. Chaque route protégée déclare la permission requise ;
 * les pages seront remplacées lot par lot (voir README).
 */
export const routes: RouteObject[] = [
  { path: '/', element: <RootRedirect /> },
  { path: PATHS.welcome, element: <WelcomePage /> },
  { path: PATHS.login, element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: PATHS.dashboard, element: <PlaceholderPage title="Vue d’ensemble" lot={2} mockup="02 / 03 — dashboards" /> },
          { path: PATHS.forbidden, element: <ForbiddenPage /> },
          { path: PATHS.profile, element: <PlaceholderPage title="Profil" lot={5} mockup="page minimale (design system)" /> },
          {
            element: <RequirePermission permission="customers:read" />,
            children: [
              { path: PATHS.clients, element: <PlaceholderPage title="Clients" lot={3} mockup="04 — clients" /> },
              { path: '/clients/:id', element: <PlaceholderPage title="Fiche client" lot={3} mockup="05 — détail client" /> },
            ],
          },
          {
            element: <RequirePermission permission="customers:write" />,
            children: [
              { path: PATHS.clientNew, element: <PlaceholderPage title="Nouveau client" lot={3} mockup="06 — formulaire client" /> },
              { path: '/clients/:id/edit', element: <PlaceholderPage title="Modifier le client" lot={3} mockup="06 — formulaire client" /> },
            ],
          },
          {
            element: <RequirePermission permission="transactions:read" />,
            children: [{ path: PATHS.transactions, element: <PlaceholderPage title="Transactions" lot={3} mockup="07 — transactions" /> }],
          },
          {
            element: <RequirePermission permission="reviews:read" />,
            children: [
              { path: PATHS.investigation, element: <PlaceholderPage title="Investigation" lot={4} mockup="08 / 08b — investigation" /> },
              { path: '/investigation/:transactionId', element: <PlaceholderPage title="Investigation" lot={4} mockup="08 / 08b — investigation" /> },
              { path: PATHS.reviews, element: <PlaceholderPage title="Smart Review" lot={4} mockup="09 — file de revue" /> },
              { path: '/reviews/:id', element: <PlaceholderPage title="Dossier de revue" lot={4} mockup="10 / 10b / 10c — décision" /> },
            ],
          },
          {
            element: <RequirePermission permission="ml:read" />,
            children: [
              { path: PATHS.ml, element: <PlaceholderPage title="Intelligence ML" lot={5} mockup="11 — performances" /> },
              { path: PATHS.mlViz, element: <PlaceholderPage title="Visualisations ML" lot={5} mockup="12 — PCA / t-SNE / UMAP" /> },
            ],
          },
          {
            element: <RequirePermission permission="notifications:read" />,
            children: [{ path: PATHS.notifications, element: <PlaceholderPage title="Notifications" lot={5} mockup="13 — notifications" /> }],
          },
          {
            element: <RequirePermission permission="users:manage" />,
            children: [{ path: PATHS.users, element: <PlaceholderPage title="Utilisateurs" lot={5} mockup="14 — utilisateurs" /> }],
          },
          {
            element: <RequirePermission permission="audit:read" />,
            children: [{ path: PATHS.audit, element: <PlaceholderPage title="Audit et traçabilité" lot={5} mockup="15 — audit" /> }],
          },
          {
            element: <RequirePermission permission="monitoring:read" />,
            children: [
              { path: PATHS.monitoring, element: <PlaceholderPage title="Monitoring" lot={5} mockup="16 — monitoring" /> },
              { path: PATHS.grafana, element: <PlaceholderPage title="Grafana" lot={5} mockup="17 — portail Grafana (lien externe)" /> },
            ],
          },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export const createAppRouter = () => createBrowserRouter(routes);
export const createTestRouter = (initialEntries: string[]) => createMemoryRouter(routes, { initialEntries });
