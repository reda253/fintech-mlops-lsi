import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { PATHS } from '@/app/router/paths';
import { customersApi } from '@/api/customers';
import type { Customer, CustomerTransaction, TransactionStatus } from '@/types/customer';
import { MOCK_CUSTOMERS, MOCK_TRANSACTIONS } from './mockCustomers';
import styles from './ClientDetailPage.module.css';

/* ── Utilitaires ───────────────────────────────────────────── */

function age(birthDate: string) {
  const b = new Date(birthDate);
  const now = new Date('2026-10-09T00:00:00Z');
  let a = now.getUTCFullYear() - b.getUTCFullYear();
  const m = now.getUTCMonth() - b.getUTCMonth();
  if (m < 0 || (m === 0 && now.getUTCDate() < b.getUTCDate())) a -= 1;
  return a;
}

function money(n: number) {
  return `${n.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD`;
}

function dateTime(iso: string) {
  const d = new Date(iso);
  const day = String(d.getUTCDate()).padStart(2, '0');
  const months = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
  return `${day} ${months[d.getUTCMonth()]} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

function statusLabel(s: TransactionStatus) {
  return s === 'APPROUVEE' ? 'APPROUVÉE' : s === 'BLOQUEE' ? 'BLOQUÉE' : 'EN_REVUE';
}

/** Construit un chemin SVG lissé à partir d'une série de valeurs. */
function sparkPath(values: number[], width = 160, height = 46) {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1 || 1);
  const pts = values.map((v, i) => [i * step, height - ((v - min) / span) * (height - 8) - 4]);
  return pts
    .map(([x, y], i) => {
      if (i === 0) return `M${x.toFixed(1)} ${y.toFixed(1)}`;
      const [px, py] = pts[i - 1];
      const cx = (px + x) / 2;
      return `C${cx.toFixed(1)} ${py.toFixed(1)} ${cx.toFixed(1)} ${y.toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
}

/* ── Sous-composants ───────────────────────────────────────── */

function StatCard({
  label,
  value,
  hint,
  tone,
  series,
}: {
  label: string;
  value: number;
  hint: string;
  tone: 'neutral' | 'success' | 'danger';
  series: number[];
}) {
  const stroke = tone === 'success' ? '#3fb950' : tone === 'danger' ? '#e5484d' : '#e8e8ec';
  return (
    <div className={styles.statCard}>
      <div className={styles.statHead}>
        <span className={styles.statIcon} aria-hidden="true">
          {tone === 'success' ? (
            <svg width="14" height="14" viewBox="0 0 16 16"><path d="M3 8.5l3.2 3.2L13 5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></svg>
          ) : tone === 'danger' ? (
            <svg width="14" height="14" viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.5"/><path d="M5.6 7V5.2a2.4 2.4 0 014.8 0V7" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 16 16"><path d="M2 5h8m0 0L7.6 2.6M10 5L7.6 7.4M14 11H6m0 0l2.4-2.4M6 11l2.4 2.4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
          )}
        </span>
        <span className={styles.statLabel}>{label}</span>
      </div>
      <div className={styles.statBody}>
        <span className={styles.statValue}>{value}</span>
        <svg className={styles.spark} viewBox="0 0 160 46" preserveAspectRatio="none" aria-hidden="true">
          <path d={sparkPath(series)} fill="none" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </div>
      <p className={styles.statHint}>{hint}</p>
    </div>
  );
}

function StatusPill({ status }: { status: TransactionStatus }) {
  const cls =
    status === 'APPROUVEE' ? styles.pillSuccess : status === 'BLOQUEE' ? styles.pillDanger : styles.pillWarning;
  return <span className={`${styles.pill} ${cls}`}>{statusLabel(status)}</span>;
}

function Probability({ value }: { value: number }) {
  const tone = value >= 0.8 ? '#e5484d' : value >= 0.4 ? '#d9a13b' : '#5a5a63';
  const pct = Math.max(4, Math.round(value * 100));
  return (
    <span className={styles.proba}>
      <span className={styles.probaValue}>{value.toFixed(2).replace('.', ',')}</span>
      <span className={styles.probaTrack}>
        <span className={styles.probaFill} style={{ width: `${pct}%`, background: tone }} />
      </span>
    </span>
  );
}

/* ── Page ──────────────────────────────────────────────────── */

export function ClientDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [transactions, setTransactions] = useState<CustomerTransaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const res = await customersApi.get(id);
        if (!alive) return;
        setCustomer(res.customer);
        setTransactions(res.transactions);
      } catch {
        if (!alive) return;
        const fallback =
          MOCK_CUSTOMERS.find((c) => c.id === id) ??
          MOCK_CUSTOMERS.find((c) => c.id === 'c-001') ??
          MOCK_CUSTOMERS[0];
        setCustomer(fallback);
        setTransactions(MOCK_TRANSACTIONS);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [id]);

  const stats = useMemo(() => {
    const approved = transactions.filter((t) => t.status === 'APPROUVEE').length;
    const blocked = transactions.filter((t) => t.status === 'BLOQUEE').length;
    const review = transactions.filter((t) => t.status === 'EN_REVUE').length;
    return { total: transactions.length, approved, blocked, review };
  }, [transactions]);

  const amounts = useMemo(() => transactions.map((t) => t.amount).reverse(), [transactions]);

  const areaChart = useMemo(() => {
    if (amounts.length < 2) return { line: '', area: '' };
    const w = 760;
    const h = 190;
    const max = Math.max(...amounts);
    const min = Math.min(...amounts);
    const span = max - min || 1;
    const step = w / (amounts.length - 1);
    const pts = amounts.map((v, i) => [i * step, h - ((v - min) / span) * (h - 34) - 10] as [number, number]);
    let line = `M${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length; i += 1) {
      const [px, py] = pts[i - 1];
      const [x, y] = pts[i];
      const cx = (px + x) / 2;
      line += ` C${cx} ${py} ${cx} ${y} ${x} ${y}`;
    }
    const area = `${line} L${w} ${h} L0 ${h} Z`;
    return { line, area };
  }, [amounts]);

  if (loading || !customer) {
    return <div className={styles.page}><p className={styles.loading}>Chargement de la fiche client…</p></div>;
  }

  const initials = `${customer.firstName.charAt(0)}${customer.lastName.charAt(0)}`.toUpperCase();

  return (
    <div className={styles.page}>
      {/* ── En-tête ─────────────────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.identity}>
          <span className={styles.bigAvatar}>{initials}</span>
          <div>
            <h1 className={styles.title}>{customer.firstName} {customer.lastName}</h1>
            <p className={styles.meta}>
              {customer.gender === 'F' ? 'Femme' : 'Homme'} · {age(customer.birthDate)} ans ·{' '}
              {customer.profession} · <span className={styles.dots}>••••</span> {customer.cardLast4}
            </p>
          </div>
        </div>
        <div className={styles.headerActions}>
          <Link to={PATHS.clientEdit(customer.id)} className={styles.outlineBtn}>
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M10.8 2.4l2.8 2.8-8 8H2.8v-2.8l8-8z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
            </svg>
            Modifier
          </Link>
          <Link to={PATHS.transactions} className={styles.primaryBtn}>
            <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M2 5h12M2 5l3-3M2 5l3 3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M14 11H2m12 0l-3-3m3 3l-3 3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Voir les transactions
          </Link>
        </div>
      </header>

      {/* ── KPI ─────────────────────────────────────────────── */}
      <div className={styles.statsRow}>
        <StatCard label="Transactions chargées" value={stats.total} hint="calculé sur la liste du client" tone="neutral" series={[4, 3, 5, 2, 4, 3, 6, 5]} />
        <StatCard label="Approuvées" value={stats.approved} hint="statut APPROUVÉE" tone="success" series={[3, 2, 4, 3, 5, 2, 4, 3]} />
        <StatCard label="Bloquées" value={stats.blocked} hint="statut BLOQUÉE" tone="danger" series={[2, 4, 1, 3, 2, 5, 2, 3]} />
        <StatCard label="En revue" value={stats.review} hint="statut EN_REVUE" tone="neutral" series={[3, 2, 1, 4, 3, 2, 5, 4]} />
      </div>

      {/* ── Corps : transactions + profil ───────────────────── */}
      <div className={styles.mainGrid}>
        {/* Transactions */}
        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2 className={styles.cardTitle}>Transactions du client</h2>
            <span className={styles.cardHint}>filtre customerId</span>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>Date</th>
                  <th className={styles.th}>Transaction</th>
                  <th className={styles.th}>Montant</th>
                  <th className={styles.th}>Catégorie</th>
                  <th className={styles.th}>Statut</th>
                  <th className={styles.th}>Probabilité</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((t) => (
                  <tr key={t.id} className={styles.row}>
                    <td className={styles.td}>{dateTime(t.occurredAt)}</td>
                    <td className={styles.td}>
                      <span className={styles.ref}>{t.reference}…</span>
                    </td>
                    <td className={styles.td}>{money(t.amount)}</td>
                    <td className={styles.td}>{t.category}</td>
                    <td className={styles.td}><StatusPill status={t.status} /></td>
                    <td className={styles.td}><Probability value={t.fraudProbability} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Profil */}
        <aside className={styles.card}>
          <div className={styles.cardHead}>
            <h2 className={styles.cardTitle}>Profil</h2>
          </div>
          <dl className={styles.profile}>
            <div className={styles.profileRow}>
              <dt>Prénom / Nom</dt>
              <dd>{customer.firstName} {customer.lastName}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Genre</dt>
              <dd>{customer.gender}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Naissance</dt>
              <dd>{customer.birthDate.slice(0, 10)}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Profession</dt>
              <dd>{customer.profession}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Adresse</dt>
              <dd>{customer.street}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Ville / État</dt>
              <dd>{customer.city}, {customer.state} {customer.zipCode}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Population de la ville</dt>
              <dd>{customer.cityPopulation.toLocaleString('fr-FR').replace(/\u202f|\u00a0/g, ' ')}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Coordonnées</dt>
              <dd>{customer.latitude.toFixed(4)}; {customer.longitude.toFixed(4)}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Carte</dt>
              <dd className={styles.cardNb}>
                <span className={styles.dots}>•••• •••• ••••</span> {customer.cardLast4}
              </dd>
            </div>
          </dl>
        </aside>
      </div>

      {/* ── Bas : montants + historique ─────────────────────── */}
      <div className={styles.bottomGrid}>
        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2 className={styles.cardTitle}>Montants des transactions</h2>
            <span className={styles.cardHint}>{transactions.length} dernières</span>
          </div>
          <div className={styles.chartWrap}>
            <svg viewBox="0 0 760 190" preserveAspectRatio="none" className={styles.areaChart} aria-hidden="true">
              <defs>
                <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ffffff" stopOpacity="0.22" />
                  <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
                </linearGradient>
              </defs>
              {[0.25, 0.5, 0.75].map((r) => (
                <line key={r} x1="0" y1={190 * r} x2="760" y2={190 * r} stroke="#1e1e22" strokeWidth="1" />
              ))}
              <path d={areaChart.area} fill="url(#areaFill)" />
              <path d={areaChart.line} fill="none" stroke="#f0f0f2" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </div>
        </section>

        <aside className={styles.card}>
          <div className={styles.cardHead}>
            <h2 className={styles.cardTitle}>Historique disponible</h2>
          </div>
          <ol className={styles.timeline}>
            <li className={styles.timelineItem}>
              <span className={`${styles.timelineDot} ${styles.dotDanger}`} />
              <div>
                <p className={styles.timelineTitle}>Dernière décision : BLOQUÉE</p>
                <p className={styles.timelineDate}>09 oct. 14:28</p>
              </div>
            </li>
            <li className={styles.timelineItem}>
              <span className={styles.timelineDot} />
              <div>
                <p className={styles.timelineTitle}>Profil mis à jour</p>
                <p className={styles.timelineDate}>2026-09-30</p>
              </div>
            </li>
            <li className={styles.timelineItem}>
              <span className={styles.timelineDot} />
              <div>
                <p className={styles.timelineTitle}>Client créé</p>
                <p className={styles.timelineDate}>{customer.createdAt.slice(0, 10)}</p>
              </div>
            </li>
          </ol>
        </aside>
      </div>
    </div>
  );
}
