import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import styles from './SmartReviewPage.module.css';

export type ReviewStatus = 'OUVERTE' | 'TRAITEE';
export type ReviewReason = 'MODELE_INCERTAIN' | 'ML_INDISPONIBLE' | 'CLIENT_INDISPONIBLE';

export interface ReviewQueueItem {
  id: string;
  transactionId: string;
  transNumShort: string;
  openedAt: string;
  openedTimestamp: number;
  amount: number;
  category: string;
  fraudProbability: number | null;
  uncertainty: number | null;
  uncertaintyLevel: 'ELEVEE' | 'MOYENNE' | 'FAIBLE' | null;
  predictionSet: string;
  reason: ReviewReason;
  status: ReviewStatus;
}

const INITIAL_REVIEWS: ReviewQueueItem[] = [
  {
    id: 'rv_2c8457',
    transactionId: 'tx-36756873',
    transNumShort: '36756873...',
    openedAt: '09 oct. 12:20',
    openedTimestamp: 1,
    amount: 310.0,
    category: 'grocery_pos',
    fraudProbability: 0.52,
    uncertainty: 0.7,
    uncertaintyLevel: 'ELEVEE',
    predictionSet: '[]',
    reason: 'MODELE_INCERTAIN',
    status: 'OUVERTE',
  },
  {
    id: 'rv_c64ea1',
    transactionId: 'tx-0101eab4',
    transNumShort: '0101eab4...',
    openedAt: '09 oct. 12:56',
    openedTimestamp: 2,
    amount: 439.26,
    category: 'gas_transport',
    fraudProbability: 0.54,
    uncertainty: 0.37,
    uncertaintyLevel: 'ELEVEE',
    predictionSet: '[0,1]',
    reason: 'MODELE_INCERTAIN',
    status: 'OUVERTE',
  },
  {
    id: 'rv_7abd2d',
    transactionId: 'tx-bd658318',
    transNumShort: 'bd658318...',
    openedAt: '09 oct. 13:32',
    openedTimestamp: 3,
    amount: 440.72,
    category: 'shopping_net',
    fraudProbability: null,
    uncertainty: null,
    uncertaintyLevel: null,
    predictionSet: '—',
    reason: 'ML_INDISPONIBLE',
    status: 'OUVERTE',
  },
  {
    id: 'rv_d752ea',
    transactionId: 'tx-fc7299f5',
    transNumShort: 'fc7299f5...',
    openedAt: '09 oct. 13:41',
    openedTimestamp: 4,
    amount: 209.74,
    category: 'shopping_net',
    fraudProbability: 0.62,
    uncertainty: 0.55,
    uncertaintyLevel: 'ELEVEE',
    predictionSet: '[0,1]',
    reason: 'MODELE_INCERTAIN',
    status: 'OUVERTE',
  },
  {
    id: 'rv_e22fb4',
    transactionId: 'tx-e1ffc95d',
    transNumShort: 'e1ffc95d...',
    openedAt: '09 oct. 14:08',
    openedTimestamp: 5,
    amount: 555.44,
    category: 'grocery_pos',
    fraudProbability: 0.45,
    uncertainty: 0.36,
    uncertaintyLevel: 'ELEVEE',
    predictionSet: '[0,1]',
    reason: 'MODELE_INCERTAIN',
    status: 'OUVERTE',
  },
  {
    id: 'rv_a8d6ef',
    transactionId: 'tx-bfc6490f',
    transNumShort: 'bfc6490f...',
    openedAt: '09 oct. 14:17',
    openedTimestamp: 6,
    amount: 820.89,
    category: 'misc_net',
    fraudProbability: 0.54,
    uncertainty: 0.37,
    uncertaintyLevel: 'ELEVEE',
    predictionSet: '[0,1]',
    reason: 'MODELE_INCERTAIN',
    status: 'OUVERTE',
  },
  {
    id: 'rv_91be04',
    transactionId: 'tx-613b9873',
    transNumShort: '613b9873...',
    openedAt: '09 oct. 11:05',
    openedTimestamp: 0,
    amount: 1329.14,
    category: 'shopping_net',
    fraudProbability: 0.93,
    uncertainty: 0.08,
    uncertaintyLevel: 'FAIBLE',
    predictionSet: '[1]',
    reason: 'MODELE_INCERTAIN',
    status: 'TRAITEE',
  },
  {
    id: 'rv_54ca19',
    transactionId: 'tx-7d67bbd1',
    transNumShort: '7d67bbd1...',
    openedAt: '09 oct. 10:14',
    openedTimestamp: -1,
    amount: 404.26,
    category: 'misc_net',
    fraudProbability: 0.5,
    uncertainty: 0.41,
    uncertaintyLevel: 'ELEVEE',
    predictionSet: '[0,1]',
    reason: 'MODELE_INCERTAIN',
    status: 'TRAITEE',
  },
];

function sparkPath(values: number[], width = 112, height = 38) {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1 || 1);
  const pts: Array<[number, number]> = values.map((v, i) => [
    i * step,
    height - ((v - min) / span) * (height - 8) - 4,
  ]);
  return pts
    .map((pt, i) => {
      const [x, y] = pt;
      if (i === 0) return `M${x.toFixed(1)} ${y.toFixed(1)}`;
      const prev = pts[i - 1] ?? pt;
      const [px, py] = prev;
      const cx = (px + x) / 2;
      return `C${cx.toFixed(1)} ${py.toFixed(1)} ${cx.toFixed(1)} ${y.toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
}

function formatMoney(n: number) {
  return `${n.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace(/\u202f|\u00a0/g, ' ')} USD`;
}

export function SmartReviewPage() {
  const [statusFilter, setStatusFilter] = useState<ReviewStatus>('OUVERTE');
  const [sortAsc, setSortAsc] = useState<boolean>(true);
  const [pageSize, setPageSize] = useState<number>(6);
  const [page, setPage] = useState<number>(1);

  const filtered = useMemo(() => {
    const list = INITIAL_REVIEWS.filter((r) => r.status === statusFilter);
    return [...list].sort((a, b) =>
      sortAsc ? a.openedTimestamp - b.openedTimestamp : b.openedTimestamp - a.openedTimestamp,
    );
  }, [statusFilter, sortAsc]);

  const totalCount = statusFilter === 'OUVERTE' ? 38 : 18;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Smart Review</h1>
          <p className={styles.subtitle}>Revues à traiter · plus anciennes d&apos;abord</p>
        </div>
        <span className={styles.roleBadge}>ANALYSTE</span>
      </header>

      <section className={styles.kpiGrid}>
        <div className={styles.kpiCard}>
          <div className={styles.kpiHead}>
            <span className={styles.kpiIcon} aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 16 16">
                <path d="M3 4.5h10M3 8h10M3 11.5h6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </span>
            <span className={styles.kpiLabel}>Revues ouvertes</span>
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiValue}>38</span>
            <svg className={styles.spark} viewBox="0 0 112 38" aria-hidden="true">
              <path
                d={sparkPath([26, 23, 15, 22, 18, 28, 30, 21])}
                fill="none"
                stroke="#e5484d"
                strokeWidth="1.7"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <p className={styles.kpiHint}>statut OUVERTE</p>
        </div>

        <div className={styles.kpiCard}>
          <div className={styles.kpiHead}>
            <span className={styles.kpiIcon} aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 16 16">
                <path d="M3.5 8.5l3 3L12.5 5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span className={styles.kpiLabel}>Traitées aujourd&apos;hui</span>
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiValue}>18</span>
            <svg className={styles.spark} viewBox="0 0 112 38" aria-hidden="true">
              <path
                d={sparkPath([19, 16, 25, 20, 29, 26, 14, 18])}
                fill="none"
                stroke="#46a758"
                strokeWidth="1.7"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <p className={styles.kpiHint}>statut TRAITEE</p>
        </div>

        <div className={styles.kpiCard}>
          <div className={styles.kpiHead}>
            <span className={styles.kpiIcon} aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 16 16">
                <rect x="3" y="2.2" width="10" height="11.6" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.4" />
                <path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
            </span>
            <span className={styles.kpiLabel}>Plus ancienne</span>
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiValue}>3 h 12</span>
            <svg className={styles.spark} viewBox="0 0 112 38" aria-hidden="true">
              <path
                d={sparkPath([15, 24, 21, 29, 27, 13, 17, 23])}
                fill="none"
                stroke="#e5e5e5"
                strokeWidth="1.7"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <p className={styles.kpiHint}>ouverte depuis</p>
        </div>

        <div className={styles.kpiCard}>
          <div className={styles.kpiHead}>
            <span className={styles.kpiIcon} aria-hidden="true">
              <svg width="14" height="14" viewBox="0 0 16 16">
                <path d="M8 2.4l5.8 10.4H2.2L8 2.4z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
                <path d="M8 6.5v3M8 11.3v.3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </span>
            <span className={styles.kpiLabel}>ML indisponible</span>
          </div>
          <div className={styles.kpiBody}>
            <span className={styles.kpiValue}>4</span>
            <svg className={styles.spark} viewBox="0 0 112 38" aria-hidden="true">
              <path
                d={sparkPath([24, 21, 12, 20, 17, 26, 28, 22])}
                fill="none"
                stroke="#e5484d"
                strokeWidth="1.7"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <p className={styles.kpiHint}>raison ML_INDISPONIBLE</p>
        </div>
      </section>

      <section className={styles.tableCard}>
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>
            <div className={styles.segmented}>
              <button
                type="button"
                className={`${styles.segBtn} ${statusFilter === 'OUVERTE' ? styles.segBtnActive : ''}`}
                onClick={() => {
                  setStatusFilter('OUVERTE');
                  setPage(1);
                }}
              >
                OUVERTE
              </button>
              <button
                type="button"
                className={`${styles.segBtn} ${statusFilter === 'TRAITEE' ? styles.segBtnActive : ''}`}
                onClick={() => {
                  setStatusFilter('TRAITEE');
                  setPage(1);
                }}
              >
                TRAITEE
              </button>
            </div>

            <button
              type="button"
              className={styles.sortChip}
              onClick={() => setSortAsc((prev) => !prev)}
            >
              <span className={styles.sortPrefix}>Tri</span>
              <span className={styles.sortValue}>ouverte le {sortAsc ? '↑' : '↓'}</span>
            </button>
          </div>

          <span className={styles.pageSizeNote}>Taille de page : 20</span>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Revue</th>
                <th className={styles.th}>Transaction</th>
                <th className={styles.th}>Ouverte le</th>
                <th className={styles.th}>Montant</th>
                <th className={styles.th}>Catégorie</th>
                <th className={styles.th}>Probabilité</th>
                <th className={styles.th}>Incertitude</th>
                <th className={styles.th}>Ensemble</th>
                <th className={styles.th}>Raison</th>
                <th className={styles.th}>Statut</th>
                <th className={styles.thAction} aria-label="Action" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.id} className={styles.row}>
                  <td className={styles.tdReviewId}>{item.id}</td>
                  <td className={styles.tdMutedMono}>{item.transNumShort}</td>
                  <td className={styles.tdDate}>{item.openedAt}</td>
                  <td className={styles.tdAmount}>{formatMoney(item.amount)}</td>
                  <td className={styles.tdCategory}>{item.category}</td>
                  <td className={styles.td}>
                    {item.fraudProbability !== null ? (
                      <div className={styles.probCell}>
                        <span className={styles.probVal}>
                          {item.fraudProbability.toFixed(2).replace('.', ',')}
                        </span>
                        <span className={styles.probTrack}>
                          <span
                            className={styles.probFill}
                            style={{ width: `${Math.round(item.fraudProbability * 100)}%` }}
                          />
                        </span>
                      </div>
                    ) : (
                      <span className={styles.dash}>—</span>
                    )}
                  </td>
                  <td className={styles.td}>
                    {item.uncertainty !== null && item.uncertaintyLevel ? (
                      <div className={styles.uncertCell}>
                        <span className={styles.uncertVal}>
                          {item.uncertainty.toFixed(2).replace('.', ',')}
                        </span>
                        <span className={`${styles.pill} ${styles.pillAmber}`}>
                          {item.uncertaintyLevel}
                        </span>
                      </div>
                    ) : (
                      <span className={styles.dash}>——</span>
                    )}
                  </td>
                  <td className={styles.td}>
                    {item.predictionSet === '—' ? (
                      <span className={`${styles.setPill} ${styles.setPillNeutral}`}>—</span>
                    ) : (
                      <span className={`${styles.setPill} ${styles.setPillAmber}`}>
                        {item.predictionSet}
                      </span>
                    )}
                  </td>
                  <td className={styles.td}>
                    <span
                      className={`${styles.pill} ${
                        item.reason === 'ML_INDISPONIBLE' ? styles.pillRed : styles.pillAmber
                      }`}
                    >
                      {item.reason}
                    </span>
                  </td>
                  <td className={styles.td}>
                    <span
                      className={`${styles.pill} ${
                        item.status === 'OUVERTE' ? styles.pillAmber : styles.pillGreen
                      }`}
                    >
                      {item.status}
                    </span>
                  </td>
                  <td className={styles.tdAction}>
                    <Link
                      to={`/investigation/${item.transactionId}`}
                      className={styles.openBtn}
                    >
                      Ouvrir
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <footer className={styles.footer}>
          <span className={styles.footerInfo}>
            1–{filtered.length} sur {totalCount} · statut {statusFilter}
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
                aria-label="Nombre de revues par page"
              >
                <option value={6}>6 / page</option>
                <option value={10}>10 / page</option>
                <option value={20}>20 / page</option>
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
    </div>
  );
}