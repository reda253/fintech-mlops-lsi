import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import styles from './NotificationsPage.module.css';

export type NotificationType = 'BLOCAGE' | 'REVUE';

export interface NotificationItem {
  id: string;
  type: NotificationType;
  title: string;
  transactionId: string;
  transNumShort: string;
  relativeTime: string;
  unread: boolean;
}

const INITIAL_NOTIFICATIONS: NotificationItem[] = [
  {
    id: 'notif-1',
    type: 'BLOCAGE',
    title: 'Transaction 1329,14 USD bloquée (probabilité de fraude 0.93)',
    transactionId: 'tx-613b9873',
    transNumShort: '613b9873...',
    relativeTime: 'il y a 2 min',
    unread: true,
  },
  {
    id: 'notif-2',
    type: 'REVUE',
    title: 'Transaction 820,89 USD envoyée en revue (raison : MODELE_INCERTAIN)',
    transactionId: 'tx-bfc6490f',
    transNumShort: 'bfc6490f...',
    relativeTime: 'il y a 11 min',
    unread: true,
  },
  {
    id: 'notif-3',
    type: 'REVUE',
    title: 'Transaction 555,44 USD envoyée en revue (raison : MODELE_INCERTAIN)',
    transactionId: 'tx-e1ffc95d',
    transNumShort: 'e1ffc95d...',
    relativeTime: 'il y a 20 min',
    unread: true,
  },
  {
    id: 'notif-4',
    type: 'BLOCAGE',
    title: 'Transaction 1709,41 USD bloquée (probabilité de fraude 0.91)',
    transactionId: 'tx-d916faba',
    transNumShort: 'd916faba...',
    relativeTime: 'il y a 1 h',
    unread: true,
  },
  {
    id: 'notif-5',
    type: 'REVUE',
    title: 'Transaction 440,72 USD envoyée en revue (raison : ML_INDISPONIBLE)',
    transactionId: 'tx-bd658318',
    transNumShort: 'bd658318...',
    relativeTime: 'il y a 1 h',
    unread: true,
  },
  {
    id: 'notif-6',
    type: 'REVUE',
    title: 'Transaction 209,74 USD envoyée en revue (raison : MODELE_INCERTAIN)',
    transactionId: 'tx-fc7299f5',
    transNumShort: 'fc7299f5...',
    relativeTime: 'il y a 3 h',
    unread: false,
  },
  {
    id: 'notif-7',
    type: 'BLOCAGE',
    title: 'Transaction 404,26 USD bloquée (probabilité de fraude 0.50)',
    transactionId: 'tx-7d67bbd1',
    transNumShort: '7d67bbd1...',
    relativeTime: 'il y a 5 h',
    unread: false,
  },
  {
    id: 'notif-8',
    type: 'REVUE',
    title: 'Transaction 439,26 USD envoyée en revue (raison : MODELE_INCERTAIN)',
    transactionId: 'tx-0101eab4',
    transNumShort: '0101eab4...',
    relativeTime: 'hier',
    unread: false,
  },
];

export function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>(INITIAL_NOTIFICATIONS);
  const [typeFilter, setTypeFilter] = useState<'Toutes' | NotificationType>('Toutes');
  const [unreadOnly, setUnreadOnly] = useState<boolean>(false);
  const [switchVisualOn, setSwitchVisualOn] = useState<boolean>(true);
  const [pageSize, setPageSize] = useState<number>(8);
  const [page, setPage] = useState<number>(1);

  const markAsRead = (id: string) => {
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, unread: false } : n)));
  };

  const counters = useMemo(() => {
    const unreadAll = items.filter((n) => n.unread).length;
    const unreadBlocage = items.filter((n) => n.unread && n.type === 'BLOCAGE').length;
    const unreadRevue = items.filter((n) => n.unread && n.type === 'REVUE').length;
    return { unreadAll, unreadBlocage, unreadRevue };
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((n) => {
      if (typeFilter !== 'Toutes' && n.type !== typeFilter) return false;
      if (unreadOnly && !n.unread) return false;
      return true;
    });
  }, [items, typeFilter, unreadOnly]);

  const totalItems = 214;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Notifications</h1>
          <p className={styles.subtitle}>Alertes BLOCAGE et REVUE</p>
        </div>

        <span className={styles.sseStatusBadge}>
          <span className={styles.greenDot} aria-hidden="true" />
          Flux temps réel connecté · authentifié
        </span>
      </header>

      <div className={styles.layout}>
        <section className={styles.mainCard}>
          <div className={styles.toolbar}>
            <div className={styles.segmented}>
              {(['Toutes', 'BLOCAGE', 'REVUE'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`${styles.segBtn} ${typeFilter === t ? styles.segBtnActive : ''}`}
                  onClick={() => {
                    setTypeFilter(t);
                    setPage(1);
                  }}
                >
                  {t}
                </button>
              ))}
            </div>

            <button
              type="button"
              className={styles.unreadToggleWrap}
              onClick={() => {
                const next = !unreadOnly;
                setUnreadOnly(next);
                setSwitchVisualOn(next);
              }}
              aria-pressed={unreadOnly}
            >
              <span className={styles.unreadToggleLabel}>Non lues seulement</span>
              <span
                className={`${styles.switchTrack} ${switchVisualOn ? styles.switchTrackOn : ''}`}
              >
                <span
                  className={`${styles.switchThumb} ${switchVisualOn ? styles.switchThumbOn : ''}`}
                />
              </span>
            </button>
          </div>

          <ul className={styles.notifList}>
            {filtered.map((notif) => (
              <li key={notif.id} className={styles.notifRow}>
                <div className={styles.notifLeft}>
                  <span className={styles.notifIcon} aria-hidden="true">
                    {notif.type === 'BLOCAGE' ? (
                      <svg width="15" height="15" viewBox="0 0 16 16">
                        <rect
                          x="3.2"
                          y="7"
                          width="9.6"
                          height="6.8"
                          rx="1.6"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.4"
                        />
                        <path
                          d="M5.5 7V5.2a2.5 2.5 0 0 1 5 0V7"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.4"
                        />
                      </svg>
                    ) : (
                      <svg width="15" height="15" viewBox="0 0 16 16">
                        <path
                          d="M3.5 4.8h9M3.5 8h9M3.5 11.2h6"
                          stroke="currentColor"
                          strokeWidth="1.4"
                          strokeLinecap="round"
                        />
                      </svg>
                    )}
                  </span>

                  <div className={styles.notifContent}>
                    <div className={styles.notifTitleLine}>
                      <span
                        className={`${styles.typePill} ${
                          notif.type === 'BLOCAGE' ? styles.pillBlocage : styles.pillRevue
                        }`}
                      >
                        {notif.type}
                      </span>
                      <span className={styles.notifTitleText}>{notif.title}</span>
                    </div>
                    <p className={styles.notifSubtext}>
                      Transaction {notif.transNumShort} · {notif.relativeTime}
                    </p>
                  </div>
                </div>

                <div className={styles.notifActions}>
                  {notif.unread && (
                    <>
                      <span className={styles.unreadDot} aria-label="Non lue" />
                      <button
                        type="button"
                        className={styles.actionBtn}
                        onClick={() => markAsRead(notif.id)}
                      >
                        Marquer comme lu
                      </button>
                    </>
                  )}
                  <Link
                    to={`/investigation/${notif.transactionId}`}
                    className={styles.actionBtn}
                  >
                    Ouvrir la transaction
                  </Link>
                </div>
              </li>
            ))}
          </ul>

          <footer className={styles.footer}>
            <span className={styles.footerInfo}>
              1–{filtered.length} sur {totalItems}
            </span>

            <div className={styles.pagination}>
              <div className={styles.pageSizeWrap}>
                <select
                  className={styles.pageSizeSelect}
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setPage(1);
                  }}
                  aria-label="Notifications par page"
                >
                  <option value={8}>8 / page</option>
                  <option value={15}>15 / page</option>
                  <option value={25}>25 / page</option>
                </select>
                <span className={styles.caret} aria-hidden="true">▼</span>
              </div>

              <button
                type="button"
                className={styles.pageBtn}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                ‹
              </button>
              {[1, 2, 3].map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`${styles.pageBtn} ${page === p ? styles.pageBtnActive : ''}`}
                  onClick={() => setPage(p)}
                >
                  {p}
                </button>
              ))}
              <span className={styles.pageDots}>…</span>
              <button
                type="button"
                className={`${styles.pageBtn} ${page === totalPages ? styles.pageBtnActive : ''}`}
                onClick={() => setPage(totalPages)}
              >
                {totalPages}
              </button>
              <button
                type="button"
                className={styles.pageBtn}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                ›
              </button>
            </div>
          </footer>
        </section>

        <aside className={styles.sideCol}>
          <section className={styles.sideCard}>
            <h2 className={styles.sideCardTitle}>Compteurs</h2>
            <dl className={styles.counterList}>
              <div className={styles.counterRow}>
                <dt>Non lues</dt>
                <dd>{counters.unreadAll}</dd>
              </div>
              <div className={styles.counterRow}>
                <dt>BLOCAGE (non lues)</dt>
                <dd>{counters.unreadBlocage}</dd>
              </div>
              <div className={styles.counterRow}>
                <dt>REVUE (non lues)</dt>
                <dd>{counters.unreadRevue}</dd>
              </div>
            </dl>
          </section>

          <section className={styles.sideCard}>
            <h2 className={styles.sideCardTitle}>Flux temps réel (SSE)</h2>
            <p className={styles.sseDescription}>
              Connexion authentifiée par l&apos;en-tête Authorization. Heartbeat toutes les 15 s.
              Les nouvelles notifications s&apos;ajoutent en tête de liste et incrémentent le
              compteur.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
