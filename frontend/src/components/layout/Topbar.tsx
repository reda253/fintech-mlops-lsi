import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { breadcrumbFor } from '@/app/navigation';
import { Badge } from '@/components/ui/Badge';
import { Icon } from '@/components/ui/Icon';
import { IconButton } from '@/components/ui/Button';
import { useAuth } from '@/features/auth/AuthContext';
import { useShellCounters } from '@/features/shell/useShellCounters';
import { config } from '@/lib/config';
import { cx } from '@/lib/cx';
import styles from './Topbar.module.css';

interface TopbarProps {
  assistantOpen: boolean;
  onToggleAssistant: () => void;
  onOpenDrawer: () => void;
}

export function Topbar({ assistantOpen, onToggleAssistant, onOpenDrawer }: TopbarProps) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const { unreadNotifications } = useShellCounters();
  const searchRef = useRef<HTMLInputElement>(null);
  const [parent, current] = breadcrumbFor(pathname);

  // Raccourci Ctrl/⌘ + K : focus sur la recherche (point d'entrée de la future palette de commandes).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!user) return null;

  return (
    <header className={styles.topbar}>
      <a href="#contenu" className={styles.skip}>
        Aller au contenu
      </a>
      <IconButton icon="menu" label="Ouvrir le menu" className={styles.burger} onClick={onOpenDrawer} />

      <nav aria-label="Fil d’Ariane" className={styles.crumbs}>
        <span>{parent}</span>
        <span aria-hidden="true"> / </span>
        <span aria-current="page" className={styles.current}>
          {current}
        </span>
      </nav>

      <div className={styles.search} role="search">
        <Icon name="search" size={18} className={styles.searchIcon} />
        <input
          ref={searchRef}
          type="search"
          className={styles.searchInput}
          placeholder="Rechercher ou saisir une commande"
          aria-label="Rechercher ou saisir une commande"
        />
        <kbd className={styles.kbd}>Ctrl K</kbd>
      </div>

      <div className={styles.actions}>
        <Badge tone="accent" className={styles.role}>
          ESPACE {user.role}
        </Badge>
        <button
          type="button"
          className={cx(styles.assistant, assistantOpen && styles.assistantOn)}
          onClick={onToggleAssistant}
          aria-pressed={assistantOpen}
        >
          <Icon name="sparkle" size={18} />
          <span>Assistant IA</span>
        </button>
        {config.useMocks && (
          <Badge dashed className={styles.simulated}>
            Données simulées
          </Badge>
        )}
        <button
          type="button"
          className={styles.bell}
          aria-label={`Notifications, ${unreadNotifications} non lues`}
        >
          <Icon name="bell" size={18} />
          {unreadNotifications > 0 && <span className={styles.bellCount}>{unreadNotifications}</span>}
        </button>
        <span className={styles.avatar} title={user.displayName} aria-label={`Connecté : ${user.displayName}`}>
          {user.initials}
        </span>
      </div>
    </header>
  );
}
