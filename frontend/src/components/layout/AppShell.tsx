import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AssistantPanel } from '@/features/assistant/AssistantPanel';
import { cx } from '@/lib/cx';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import styles from './AppShell.module.css';

/** Coque applicative : sidebar persistante, topbar sticky, contenu, panneau d'assistant IA. */
export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  return (
    <div className={cx(styles.shell, collapsed && styles.collapsed, assistantOpen && styles.withAssistant)}>
      <Sidebar
        collapsed={collapsed}
        drawerOpen={drawerOpen}
        onToggleCollapsed={() => setCollapsed((v) => !v)}
        onCloseDrawer={() => setDrawerOpen(false)}
      />
      {drawerOpen && <div className={styles.scrim} onClick={() => setDrawerOpen(false)} aria-hidden="true" />}
      <div className={styles.main}>
        <Topbar
          assistantOpen={assistantOpen}
          onToggleAssistant={() => setAssistantOpen((v) => !v)}
          onOpenDrawer={() => setDrawerOpen(true)}
        />
        <main id="contenu" className={styles.content} tabIndex={-1}>
          <Outlet />
        </main>
      </div>
      {assistantOpen && <AssistantPanel onClose={() => setAssistantOpen(false)} />}
    </div>
  );
}
