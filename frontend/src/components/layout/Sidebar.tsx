import { NavLink, useNavigate } from 'react-router-dom';
import { LogoMark, Logo } from '@/components/brand/Logo';
import { IconButton } from '@/components/ui/Button';
import { Icon } from '@/components/ui/Icon';
import { CountPill } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { navigationFor, OTHER_ITEMS, type NavItem } from '@/app/navigation';
import { PATHS } from '@/app/router/paths';
import { useAuth } from '@/features/auth/AuthContext';
import { useShellCounters } from '@/features/shell/useShellCounters';
import { can } from '@/lib/permissions';
import { cx } from '@/lib/cx';
import styles from './Sidebar.module.css';

interface SidebarProps {
  collapsed: boolean;
  drawerOpen: boolean;
  onToggleCollapsed: () => void;
  onCloseDrawer: () => void;
}

export function Sidebar({ collapsed, drawerOpen, onToggleCollapsed, onCloseDrawer }: SidebarProps) {
  const { user, logout } = useAuth();
  const counters = useShellCounters();
  const navigate = useNavigate();

  if (!user) return null;
  const sections = navigationFor(user.role)
    .map((s) => ({ ...s, items: s.items.filter((i) => !i.permission || can(user.role, i.permission)) }))
    .filter((s) => s.items.length > 0);

  const renderItem = (item: NavItem) => {
    const count = item.counter ? counters[item.counter] : undefined;
    return (
      <li key={item.to}>
        <NavLink
          to={item.to}
          className={({ isActive }) => cx(styles.item, isActive && styles.active)}
          title={collapsed ? item.label : undefined}
          aria-label={collapsed ? item.label : undefined}
        >
          <Icon name={item.icon} size={20} className={styles.icon} />
          <span className={styles.label}>{item.label}</span>
          {count !== undefined && !collapsed && <CountPill value={count} />}
        </NavLink>
      </li>
    );
  };

  const handleLogout = async () => {
    await logout();
    navigate(PATHS.login, { replace: true });
  };

  return (
    <aside
      className={cx(styles.sidebar, collapsed && styles.isCollapsed, drawerOpen && styles.open)}
      aria-label="Barre latérale"
    >
      <div className={styles.head}>
        {collapsed ? <LogoMark height={30} /> : <Logo />}
        <IconButton
          icon="panel"
          label={collapsed ? 'Déployer la barre latérale' : 'Réduire la barre latérale'}
          className={styles.toggle}
          onClick={onToggleCollapsed}
          size={18}
        />
        <IconButton icon="close" label="Fermer le menu" className={styles.closeDrawer} onClick={onCloseDrawer} />
      </div>

      <nav className={styles.nav} aria-label="Navigation principale">
        {sections.map((section) => (
          <div key={section.title} className={styles.section}>
            <p className={styles.sectionTitle}>{section.title}</p>
            <ul>{section.items.map(renderItem)}</ul>
          </div>
        ))}
        <div className={styles.section}>
          <p className={styles.sectionTitle}>Autre</p>
          <ul>
            {OTHER_ITEMS.map(renderItem)}
            <li>
              <button
                type="button"
                className={styles.item}
                onClick={handleLogout}
                title={collapsed ? 'Déconnexion' : undefined}
                aria-label={collapsed ? 'Déconnexion' : undefined}
              >
                <Icon name="logout" size={20} className={styles.icon} />
                <span className={styles.label}>Déconnexion</span>
              </button>
            </li>
          </ul>
        </div>
      </nav>

      {!collapsed && (
        <div className={styles.model}>
          <div className={styles.modelHead}>
            <Icon name="sparkle" size={20} />
            <div>
              <p className={styles.modelTitle}>Modèle en production</p>
              <p className={styles.modelSub}>fraud-detector · v8</p>
            </div>
          </div>
          <Button block onClick={() => navigate(PATHS.ml)}>
            Voir le modèle
          </Button>
        </div>
      )}
    </aside>
  );
}
