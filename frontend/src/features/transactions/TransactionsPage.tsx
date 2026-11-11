import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { PATHS } from '@/app/router/paths';
import { transactionsApi } from '@/api/transactions';
import { MOCK_CUSTOMERS } from '@/features/customers/mockCustomers';
import type { FullTransactionStatus, TransactionItem } from '@/types/transaction';
import { MOCK_TRANSACTIONS_LIST, MOCK_TRANSACTIONS_TOTAL } from './mockTransactions';
import styles from './TransactionsPage.module.css';

const STATUS_OPTIONS: Array<{ value: 'Tous' | FullTransactionStatus; label: string }> = [
  { value: 'Tous', label: 'Tous' },
  { value: 'EN_ATTENTE', label: 'EN_ATTENTE' },
  { value: 'EN_REVUE', label: 'EN_REVUE' },
  { value: 'APPROUVEE', label: 'APPROUVEE' },
  { value: 'BLOQUEE', label: 'BLOQUEE' },
];

const QUICK_STATUSES: FullTransactionStatus[] = [
  'EN_ATTENTE',
  'EN_REVUE',
  'APPROUVEE',
  'BLOQUEE',
];

function formatDateTime(iso: string) {
  const d = new Date(iso);
  const day = String(d.getUTCDate()).padStart(2, '0');
  const months = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
  return `${day} ${months[d.getUTCMonth()]} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

function formatMoney(n: number) {
  return `${n.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace(/\u202f|\u00a0/g, '')} USD`;
}

function initials(first: string, last: string) {
  return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
}

function shortRef(transNum: string) {
  return `${transNum.slice(0, 8)}...`;
}

function formatPredictionSet(set: number[] | null | undefined) {
  if (!set) return '—';
  if (set.length === 0) return '[]';
  return `[${set.join(',')}]`;
}

function StatusBadge({ status }: { status: FullTransactionStatus }) {
  const cls =
    status === 'APPROUVEE'
      ? styles.pillApproved
      : status === 'BLOQUEE'
        ? styles.pillBlocked
        : status === 'EN_REVUE'
          ? styles.pillReview
          : styles.pillPending;
  return <span className={`${styles.statusPill} ${cls}`}>{status}</span>;
}

function ProbabilityCell({ value }: { value: number | null }) {
  if (value === null || value === undefined) {
    return <span className={styles.probaEmpty}>—</span>;
  }
  const color = value >= 0.8 ? '#e5484d' : value >= 0.4 ? '#d99b26' : '#4a4a4f';
  const pct = Math.max(6, Math.round(value * 100));
  return (
    <span className={styles.proba}>
      <span className={styles.probaNum}>{value.toFixed(2).replace('.', ',')}</span>
      <span className={styles.probaBar}>
        <span className={styles.probaFill} style={{ width: `${pct}%`, background: color }} />
      </span>
    </span>
  );
}

export function TransactionsPage() {
  const [searchParams] = useSearchParams();
  const initialCustomer = searchParams.get('customerId') ?? 'Tous';

  const [customerId, setCustomerId] = useState<string>(initialCustomer);
  const [status, setStatus] = useState<'Tous' | FullTransactionStatus>('Tous');
  const [minAmount, setMinAmount] = useState<string>('0');
  const [maxAmount, setMaxAmount] = useState<string>('');
  const [period, setPeriod] = useState<string>('2026-10-03_2026-10-09');

  const [applied, setApplied] = useState({
    customerId: initialCustomer,
    status: 'Tous' as 'Tous' | FullTransactionStatus,
    minAmount: '0',
    maxAmount: '',
  });

  const [items, setItems] = useState<TransactionItem[]>([]);
  const [total, setTotal] = useState<number>(MOCK_TRANSACTIONS_TOTAL);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedId, setSelectedId] = useState<string>('tx-613b9873');

  const load = useCallback(async () => {
    setLoading(true);
    const minVal = applied.minAmount.trim() ? Number(applied.minAmount) : undefined;
    const maxVal = applied.maxAmount.trim() ? Number(applied.maxAmount) : undefined;
    try {
      const res = await transactionsApi.list({
        customerId: applied.customerId === 'Tous' ? undefined : applied.customerId,
        status: applied.status === 'Tous' ? undefined : applied.status,
        minAmount: minVal && minVal > 0 ? minVal : undefined,
        maxAmount: maxVal,
        page,
        pageSize,
      });
      setItems(res.items);
      setTotal(res.total);
      const firstItem = res.items[0];
      if (firstItem) {
        setSelectedId((prev) => (res.items.some((x) => x.id === prev) ? prev : firstItem.id));
      }
    } catch {
      const filtered = MOCK_TRANSACTIONS_LIST.filter((tx) => {
        if (applied.customerId !== 'Tous' && tx.customerId !== applied.customerId) return false;
        if (applied.status !== 'Tous' && tx.status !== applied.status) return false;
        if (minVal !== undefined && !Number.isNaN(minVal) && tx.amount < minVal) return false;
        if (maxVal !== undefined && !Number.isNaN(maxVal) && tx.amount > maxVal) return false;
        return true;
      });
      const isFiltered =
        applied.customerId !== 'Tous' ||
        applied.status !== 'Tous' ||
        (minVal !== undefined && minVal > 0) ||
        maxVal !== undefined;
      setItems(filtered);
      setTotal(isFiltered ? filtered.length : MOCK_TRANSACTIONS_TOTAL);
      const firstFiltered = filtered[0];
      if (firstFiltered) {
        setSelectedId((prev) => (filtered.some((x) => x.id === prev) ? prev : firstFiltered.id));
      }
    } finally {
      setLoading(false);
    }
  }, [applied, page, pageSize]);

  useEffect(() => {
    void load();
    if (import.meta.env.VITE_USE_MOCKS === 'false') {
      const timer = window.setInterval(() => {
        void load();
      }, 5000);
      return () => window.clearInterval(timer);
    }
    return undefined;
  }, [load]);

  const applyFilters = () => {
    setPage(1);
    setApplied({ customerId, status, minAmount, maxAmount });
  };

  const resetFilters = () => {
    setCustomerId('Tous');
    setStatus('Tous');
    setMinAmount('0');
    setMaxAmount('');
    setPage(1);
    setApplied({ customerId: 'Tous', status: 'Tous', minAmount: '0', maxAmount: '' });
  };

  const toggleQuickStatus = (target: FullTransactionStatus) => {
    const next = status === target ? 'Tous' : target;
    setStatus(next);
    setPage(1);
    setApplied((prev) => ({ ...prev, status: next }));
  };

  const selected = useMemo(
    () => items.find((x) => x.id === selectedId) ?? items[0] ?? MOCK_TRANSACTIONS_LIST[0],
    [items, selectedId],
  );

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);
  const totalPagesFormatted = totalPages.toLocaleString('fr-FR').replace(/\u202f|\u00a0/g, ' ');
  const totalPagesParts = totalPagesFormatted.split(' ');

  return (
    <div className={styles.page}>
      {/* ── En-tête ─────────────────────────────────────────── */}
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Transactions</h1>
          <p className={styles.subtitle}>
            {total.toLocaleString('fr-FR').replace(/\u202f|\u00a0/g, ' ')} transactions
          </p>
        </div>
        <span className={styles.readonlyBadge}>
          Consultation seule · pas de création manuelle
        </span>
      </header>

      {/* ── Carte des filtres ───────────────────────────────── */}
      <section className={styles.filterCard}>
        <div className={styles.filterRow}>
          <div className={styles.selectChip}>
            <span className={styles.chipPrefix}>Client</span>
            <select
              className={styles.chipSelect}
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              aria-label="Filtrer par client"
            >
              <option value="Tous">Tous</option>
              {MOCK_CUSTOMERS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.firstName} {c.lastName}
                </option>
              ))}
            </select>
            <span className={styles.caret} aria-hidden="true">▼</span>
          </div>

          <div className={styles.selectChip}>
            <span className={styles.chipPrefix}>Statut</span>
            <select
              className={styles.chipSelect}
              value={status}
              onChange={(e) => setStatus(e.target.value as 'Tous' | FullTransactionStatus)}
              aria-label="Filtrer par statut"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <span className={styles.caret} aria-hidden="true">▼</span>
          </div>

          <label className={styles.amountChip}>
            <span className={styles.chipPrefix}>Montant min</span>
            <input
              type="text"
              inputMode="decimal"
              className={styles.amountInput}
              value={minAmount}
              onChange={(e) => setMinAmount(e.target.value.replace(/[^0-9.]/g, ''))}
              placeholder="0"
            />
          </label>

          <label className={styles.amountChip}>
            <span className={styles.chipPrefix}>Montant max</span>
            <input
              type="text"
              inputMode="decimal"
              className={styles.amountInput}
              value={maxAmount}
              onChange={(e) => setMaxAmount(e.target.value.replace(/[^0-9.]/g, ''))}
              placeholder="—"
            />
          </label>

          <div className={styles.selectChip}>
            <svg width="14" height="14" viewBox="0 0 16 16" className={styles.calendarIcon} aria-hidden="true">
              <rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="1.4" />
              <path d="M5 1.8v2.4M11 1.8v2.4M2 6.5h12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
            <select
              className={styles.chipSelect}
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              aria-label="Période"
            >
              <option value="2026-10-03_2026-10-09">Du 03 oct. au 09 oct.</option>
              <option value="2026-10-01_2026-10-09">Du 01 oct. au 09 oct.</option>
              <option value="all">Toute la période</option>
            </select>
            <span className={styles.caret} aria-hidden="true">▼</span>
          </div>

          <button type="button" className={styles.applyBtn} onClick={applyFilters}>
            Appliquer
          </button>
          <button type="button" className={styles.resetBtn} onClick={resetFilters}>
            Réinitialiser
          </button>
        </div>

        <div className={styles.quickTags}>
          {QUICK_STATUSES.map((st) => {
            const active = applied.status === st;
            const toneClass =
              st === 'APPROUVEE'
                ? styles.pillApproved
                : st === 'BLOQUEE'
                  ? styles.pillBlocked
                  : st === 'EN_REVUE'
                    ? styles.pillReview
                    : styles.pillPending;
            return (
              <button
                key={st}
                type="button"
                className={`${styles.statusPill} ${toneClass} ${styles.quickTagBtn} ${active ? styles.quickTagActive : ''}`}
                onClick={() => toggleQuickStatus(st)}
              >
                {st}
              </button>
            );
          })}
        </div>
      </section>

      {/* ── Grille principale : Tableau + Panneau de détail ── */}
      <div className={styles.mainGrid}>
        <section className={styles.card}>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>Date</th>
                  <th className={styles.th}>N° transaction</th>
                  <th className={styles.th}>Client</th>
                  <th className={styles.th}>Montant</th>
                  <th className={styles.th}>Catégorie</th>
                  <th className={styles.th}>Statut</th>
                  <th className={styles.th}>Source</th>
                  <th className={styles.th}>Probabilité</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td className={styles.emptyCell} colSpan={8}>
                      Chargement des transactions…
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td className={styles.emptyCell} colSpan={8}>
                      Aucune transaction ne correspond aux filtres sélectionnés.
                    </td>
                  </tr>
                ) : (
                  items.map((tx) => {
                    const isSelected = selected?.id === tx.id;
                    return (
                      <tr
                        key={tx.id}
                        className={`${styles.row} ${isSelected ? styles.rowSelected : ''}`}
                        onClick={() => setSelectedId(tx.id)}
                      >
                        <td className={styles.tdDate}>{formatDateTime(tx.transDateTime)}</td>
                        <td className={styles.td}>
                          <span className={styles.txRef}>{shortRef(tx.transNum)}</span>
                        </td>
                        <td className={styles.td}>
                          <div className={styles.clientBlock}>
                            <div className={styles.clientTopLine}>
                              <span className={styles.avatar}>
                                {initials(tx.customerFirstName, tx.customerLastName)}
                              </span>
                              <span className={styles.clientName}>
                                {tx.customerFirstName} {tx.customerLastName}
                              </span>
                            </div>
                            <span className={styles.clientCard}>•••• {tx.cardLast4}</span>
                          </div>
                        </td>
                        <td className={styles.tdAmount}>{formatMoney(tx.amount)}</td>
                        <td className={styles.td}>{tx.category}</td>
                        <td className={styles.td}>
                          <StatusBadge status={tx.status} />
                        </td>
                        <td className={styles.td}>
                          {tx.decisionSource === 'MANUELLE' ? (
                            <span className={styles.sourceManual}>MANUELLE</span>
                          ) : (
                            <span className={styles.sourceAuto}>{tx.decisionSource ?? 'AUTO'}</span>
                          )}
                        </td>
                        <td className={styles.td}>
                          <ProbabilityCell value={tx.risk?.fraudProbability ?? null} />
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <footer className={styles.footer}>
            <p className={styles.footerText}>
              {first}–{last} sur {total.toLocaleString('fr-FR').replace(/\u202f|\u00a0/g, ' ')} · tri : date ↓
            </p>
            <div className={styles.pagination}>
              <div className={styles.pageSizeWrap}>
                <select
                  className={styles.pageSizeSelect}
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setPage(1);
                  }}
                >
                  <option value={10}>10 / page</option>
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                </select>
                <span className={styles.caretSmall} aria-hidden="true">▼</span>
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
              <button type="button" className={styles.pageBtn} disabled>
                …
              </button>
              <button
                type="button"
                className={`${styles.pageBtn} ${styles.pageBtnStacked}`}
                onClick={() => setPage(totalPages)}
              >
                {totalPagesParts.length > 1 ? (
                  <>
                    <span>{totalPagesParts[0]}</span>
                    <span>{totalPagesParts.slice(1).join('')}</span>
                  </>
                ) : (
                  <span>{totalPagesFormatted}</span>
                )}
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

        {/* ── Panneau latéral droit : Détail de la transaction ── */}
        {selected && (
          <aside className={styles.detailCard}>
            <div className={styles.detailHeader}>
              <h2 className={styles.detailTitle}>Transaction {shortRef(selected.transNum)}</h2>
              <StatusBadge status={selected.status} />
            </div>

            <dl className={styles.detailList}>
              <div className={styles.detailRow}>
                <dt>Client</dt>
                <dd>
                  {selected.customerFirstName} {selected.customerLastName} · •••• {selected.cardLast4}
                </dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Montant</dt>
                <dd>{formatMoney(selected.amount)}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Date</dt>
                <dd>{formatDateTime(selected.transDateTime)}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Catégorie</dt>
                <dd>{selected.category}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Marchand</dt>
                <dd>{selected.merchant}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Position marchand</dt>
                <dd>
                  {selected.merchLat.toFixed(4)} ; {selected.merchLong.toFixed(4)}
                </dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Source</dt>
                <dd>{selected.decisionSource ?? 'AUTO'}</dd>
              </div>
            </dl>

            <h3 className={styles.subSectionTitle}>Évaluation du risque</h3>

            <dl className={styles.detailList}>
              <div className={styles.detailRow}>
                <dt>Décision</dt>
                <dd>{selected.risk?.decision ?? '—'}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Raison</dt>
                <dd>{selected.risk?.reason ?? '—'}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Probabilité de fraude</dt>
                <dd>
                  {selected.risk?.fraudProbability !== null && selected.risk?.fraudProbability !== undefined
                    ? selected.risk.fraudProbability.toFixed(2).replace('.', ',')
                    : '—'}
                </dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Ensemble de prédiction</dt>
                <dd>{formatPredictionSet(selected.risk?.predictionSet)}</dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Incertitude</dt>
                <dd>
                  {selected.risk?.uncertainty !== null && selected.risk?.uncertainty !== undefined
                    ? `${selected.risk.uncertainty.toFixed(2).replace('.', ',')} (${selected.risk.uncertaintyLevel ?? 'FAIBLE'})`
                    : '—'}
                </dd>
              </div>
              <div className={styles.detailRow}>
                <dt>Modèle</dt>
                <dd>{selected.risk?.modelVersion ?? '—'}</dd>
              </div>
            </dl>

            <Link to={PATHS.investigationOf(selected.id)} className={styles.detailCta}>
              <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">
                <path
                  d="M8 1.5l1.6 4.4L14 7.5l-4.4 1.6L8 13.5 6.4 9.1 2 7.5l4.4-1.6L8 1.5z"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinejoin="round"
                />
              </svg>
              Voir la fiche détaillée
            </Link>
          </aside>
        )}
      </div>
    </div>
  );
}
