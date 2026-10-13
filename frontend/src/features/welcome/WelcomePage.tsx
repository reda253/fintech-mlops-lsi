import { useNavigate } from 'react-router-dom';
import { PATHS } from '@/app/router/paths';
import logoComposition from '@/assets/00_COMMUN_logo.png';
import styles from './WelcomePage.module.css';

/**
 * Écran d'accueil affiché avant la connexion.
 * La composition (logo + 4 déclinaisons) est le PNG original, non modifié.
 * Aucune redirection automatique : l'utilisateur clique pour continuer.
 */
export function WelcomePage() {
  const navigate = useNavigate();

  return (
    <main className={styles.page}>
      <div className={styles.stage}>
        <img
          className={styles.composition}
          src={logoComposition}
          width={3200}
          height={1800}
          alt="FinTech Risk Intelligence — logo principal et déclinaisons : icône (sidebar réduite), favicon 32 px, favicon 16 px, sur fond clair"
          draggable={false}
        />

        {/* Décorations : calques séparés, au-dessus du PNG, non interactifs. */}
        <div className={styles.halo} aria-hidden="true" />
        <div className={styles.particles} aria-hidden="true">
          {Array.from({ length: 8 }, (_, i) => (
            <span key={i} className={styles.particle} />
          ))}
        </div>

        <div className={styles.actions}>
          <button type="button" className={styles.cta} onClick={() => navigate(PATHS.login)}>
            Accéder à la plateforme
          </button>
        </div>
      </div>
    </main>
  );
}
