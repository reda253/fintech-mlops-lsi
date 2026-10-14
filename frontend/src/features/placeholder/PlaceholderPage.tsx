import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { useAuth } from '@/features/auth/AuthContext';
import styles from './PlaceholderPage.module.css';

interface PlaceholderPageProps {
  title: string;
  /** Lot du plan de réalisation qui livrera la vraie page. */
  lot: 2 | 3 | 4 | 5;
  mockup: string;
}

/** Page provisoire : route, garde et navigation sont réels ; le contenu arrive dans le lot indiqué. */
export function PlaceholderPage({ title, lot, mockup }: PlaceholderPageProps) {
  const { user } = useAuth();
  return (
    <div className={styles.wrap}>
      <p className={styles.eyebrow}>Connecté en tant que {user?.role}</p>
      <h1 className={styles.title}>{title}</h1>
      <Card className={styles.card}>
        <Badge tone="accent">Lot {lot}</Badge>
        <p className={styles.text}>
          Cette page sera reconstruite fidèlement d’après <code>{mockup}</code> au Lot {lot}. Le routage, les droits
          d’accès et la navigation sont déjà en place.
        </p>
      </Card>
    </div>
  );
}
