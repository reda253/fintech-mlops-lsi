import { Badge } from '@/components/ui/Badge';
import { IconButton } from '@/components/ui/Button';
import { Icon } from '@/components/ui/Icon';
import { useAuth } from '@/features/auth/AuthContext';
import styles from './AssistantPanel.module.css';

const SUGGESTIONS = ['Résume la semaine', 'Quelles catégories sont à risque ?', 'Compare avec la semaine précédente'];

/**
 * Panneau « Assistant IA » — interface SIMULÉE (maquette 02/03).
 * Point d'extension : remplacer `SIMULATED_REPLY` par un appel à un backend IA sécurisé
 * (contexte = route + entité consultée). L'assistant explique des données ; il ne décide jamais
 * d'approuver ou de bloquer une transaction.
 */
export function AssistantPanel({ onClose }: { onClose: () => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  return (
    <aside className={styles.panel} aria-label="Assistant IA">
      <header className={styles.head}>
        <Icon name="sparkle" size={18} className={styles.spark} />
        <h2 className={styles.title}>Assistant IA</h2>
        <Badge>Facultatif</Badge>
        <IconButton icon="close" label="Fermer l’assistant" className={styles.close} onClick={onClose} />
      </header>

      <p className={styles.context}>
        Contexte : <strong>{isAdmin ? 'Dashboard global' : 'Dashboard risques'}</strong>
      </p>

      <div className={styles.thread}>
        <p className={styles.user}>
          {isAdmin ? 'Pourquoi le taux de blocage a-t-il varié ?' : 'Quelles revues traiter en premier ?'}
        </p>
        <div className={styles.bot}>
          <p>
            {isAdmin
              ? 'Le taux de blocage reste autour de 1,8 % sur 7 jours, avec un maximum de 2,3 % mercredi. Les catégories shopping_net et misc_net concentrent la part à risque la nuit.'
              : 'Réponse illustrative : le service IA réel n’est pas encore connecté. Il s’appuiera sur les données de la file de revue.'}
          </p>
          <p className={styles.note}>Réponse simulée · questions prédéfinies</p>
        </div>
      </div>

      <p className={styles.sugTitle}>Questions suggérées</p>
      <ul className={styles.chips}>
        {SUGGESTIONS.map((s) => (
          <li key={s}>
            <button type="button" className={styles.chip}>
              {s}
            </button>
          </li>
        ))}
      </ul>

      <p className={styles.disclaimer}>L’assistant explique les données ; il ne modifie rien.</p>

      <div className={styles.footer}>
        <div className={styles.ask}>
          <input className={styles.askInput} placeholder="Posez une question…" aria-label="Poser une question" />
          <button type="button" className={styles.send} aria-label="Envoyer" disabled>
            <Icon name="send" size={16} />
          </button>
        </div>
        <p className={styles.zone}>Zone d’intégration · service IA à connecter</p>
      </div>
    </aside>
  );
}
