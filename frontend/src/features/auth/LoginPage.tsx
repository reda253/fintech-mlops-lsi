import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { PATHS } from '@/app/router/paths';
import { ApiError } from '@/api/errors';
import { Logo } from '@/components/brand/Logo';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Icon } from '@/components/ui/Icon';
import { useAuth } from './AuthContext';
import { RadarPanel } from './RadarPanel';
import styles from './LoginPage.module.css';

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.kind === 'unauthenticated') {
      return 'Identifiants invalides. Vérifiez votre nom d’utilisateur et votre mot de passe.';
    }
    if (error.kind === 'rate_limited') return 'Trop de tentatives. Patientez quelques instants avant de réessayer.';
    return 'Le service d’authentification est momentanément indisponible. Réessayez dans un instant.';
  }
  return 'Une erreur inattendue est survenue. Réessayez.';
}

export function LoginPage() {
  const { status, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (status === 'authenticated') return <Navigate to={from ?? PATHS.dashboard} replace />;

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (pending) return;
    if (!username.trim() || !password) {
      setError('Renseignez votre nom d’utilisateur et votre mot de passe.');
      return;
    }
    setPending(true);
    setError(null);
    try {
      await login({ username, password });
      navigate(from ?? PATHS.dashboard, { replace: true });
    } catch (e) {
      setError(messageFor(e));
      setPending(false);
    }
  };

  return (
    <div className={styles.page}>
      <RadarPanel />
      <div className={styles.right}>
        <div className={styles.card}>
          <Logo large />
          <h1 className={styles.title}>Bienvenue</h1>
          <p className={styles.sub}>Connectez-vous pour accéder à votre espace.</p>

          <form onSubmit={onSubmit} noValidate className={styles.form}>
            {error && <Alert>{error}</Alert>}
            <Field
              label="Nom d’utilisateur"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={username}
              invalid={!!error}
              onChange={(e) => setUsername(e.target.value)}
            />
            <Field
              label="Mot de passe"
              name="password"
              type="password"
              revealable
              autoComplete="current-password"
              value={password}
              invalid={!!error}
              onChange={(e) => setPassword(e.target.value)}
            />
            <div className={styles.forgot}>
              <button
                type="button"
                className={styles.link}
                title="Non disponible dans cette version de démonstration"
                aria-disabled="true"
              >
                Mot de passe oublié ?
              </button>
            </div>
            <Button type="submit" variant="primary" size="lg" block disabled={pending}>
              {pending ? 'Connexion…' : 'Se connecter'}
            </Button>
          </form>

          <p className={styles.note}>
            <Icon name="lock" size={13} />
            <span>Connexion sécurisée · le rôle est attribué automatiquement</span>
          </p>
        </div>
      </div>
    </div>
  );
}
