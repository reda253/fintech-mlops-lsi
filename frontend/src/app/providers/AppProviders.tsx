import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { AuthProvider } from '@/features/auth/AuthContext';
import type { AuthService } from '@/features/auth/authService';

interface AppProvidersProps {
  authService: AuthService;
  children: ReactNode;
}

/** Composition des providers globaux : session, cache de données (TanStack Query). */
export function AppProviders({ authService, children }: AppProvidersProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            // Pas de nouvelle tentative sur 401/403/404 : inutile et masque l'erreur.
            retry: (count, error) => {
              const status = (error as { status?: number }).status ?? 500;
              return status >= 500 && count < 2;
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider service={authService}>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
