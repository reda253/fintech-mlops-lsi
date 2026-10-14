import '@fontsource-variable/inter';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
import './styles/tokens.css';
import './styles/base.css';
import { AppProviders } from './app/providers/AppProviders';
import { createAppRouter } from './app/router/routes';
import { createDemoAuthService, createJwtAuthService } from './features/auth/authService';
import { config } from './lib/config';

async function enableMocking() {
  if (!config.useMocks) return;
  const { worker } = await import('./mocks/browser');
  await worker.start({ onUnhandledRequest: 'bypass', quiet: true });
}

const authService = config.authMode === 'jwt' ? createJwtAuthService() : createDemoAuthService();
const router = createAppRouter();

enableMocking()
  .catch((error) => console.warn('MSW indisponible, poursuite sans API fictives.', error))
  .finally(() => {
    createRoot(document.getElementById('root')!).render(
      <StrictMode>
        <AppProviders authService={authService}>
          <RouterProvider router={router} />
        </AppProviders>
      </StrictMode>,
    );
  });
