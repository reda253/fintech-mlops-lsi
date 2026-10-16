import { Link } from 'react-router-dom';
import { PATHS } from '@/app/router/paths';
import { Card } from '@/components/ui/Card';
import styles from './PlaceholderPage.module.css';

/** Écrans 403 / 404 provisoires (le rendu fidèle à la maquette 18 est prévu au Lot 5). */
function StatusScreen({ code, title, text }: { code: string; title: string; text: string }) {
  return (
    <div className={styles.wrap}>
      <p className={styles.eyebrow}>Erreur {code}</p>
      <h1 className={styles.title}>{title}</h1>
      <Card className={styles.card}>
        <p className={styles.text}>{text}</p>
        <Link to={PATHS.dashboard} className={styles.text} style={{ color: 'var(--color-text)', textDecoration: 'underline' }}>
          Retour au dashboard
        </Link>
      </Card>
    </div>
  );
}

export const ForbiddenPage = () => (
  <StatusScreen code="403" title="Accès interdit" text="Votre rôle ne permet pas d’accéder à cette page." />
);

export const NotFoundPage = () => (
  <StatusScreen code="404" title="Page introuvable" text="Cette adresse n’existe pas ou a été déplacée." />
);
