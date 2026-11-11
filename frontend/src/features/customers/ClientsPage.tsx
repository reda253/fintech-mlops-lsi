import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PATHS } from '@/app/router/paths';
import { customersApi } from '@/api/customers';
import type { Customer, CustomerListResponse } from '@/types/customer';
import { MOCK_CUSTOMERS, MOCK_TOTAL } from './mockCustomers';
import styles from './ClientsPage.module.css';

const STATE_OPTIONS = ['Tous', 'NC', 'GA', 'VA', 'FL', 'TN', 'SC', 'OH'];

function initials(c: Customer) {
  return `${c.firstName.charAt(0)}${c.lastName.charAt(0)}`.toUpperCase();
}

export function ClientsPage() {
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('Tous');
  const [cardLast4, setCardLast4] = useState('');

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [loading, setLoading] = useState(true);

  const [applied, setApplied] = useState({ name: '', city: '', state: 'Tous', cardLast4: '' });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res: CustomerListResponse = await customersApi.list({
        q: applied.name || undefined,
        city: applied.city || undefined,
        state: applied.state === 'Tous' ? undefined : applied.state,
        cardLast4: applied.cardLast4 || undefined,
        page,
        pageSize,
        sortBy: 'createdAt',
        sortDir: 'desc',
      });
      setCustomers(res.items);
      setTotal(res.total);
    } catch {
      const filtered = MOCK_CUSTOMERS.filter((c) => {
        const full = `${c.firstName} ${c.lastName}`.toLowerCase();
        if (applied.name && !full.includes(applied.name.toLowerCase())) return false;
        if (applied.city && !c.city.toLowerCase().includes(applied.city.toLowerCase())) return false;
        if (applied.state !== 'Tous' && c.state !== applied.state) return false;
        if (applied.cardLast4 && !c.cardLast4.includes(applied.cardLast4)) return false;
        return true;
      });
      const filteredActive =
        applied.name || applied.city || applied.cardLast4 || applied.state !== 'Tous';
      setCustomers(filtered);
      setTotal(filteredActive ? filtered.length : MOCK_TOTAL);
    } finally {
      setLoading(false);
    }
  }, [applied, page, pageSize]);

  useEffect(() => {
    void load();
  }, [load]);

  const search = () => {
    setPage(1);
    setApplied({ name, city, state, cardLast4 });
  };

  const reset = () => {
    setName('');
    setCity('');
    setState('Tous');
    setCardLast4('');
    setPage(1);
    setApplied({ name: '', city: '', state: 'Tous', cardLast4: '' });
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  const pageButtons = useMemo(() => {
    const out: number[] = [];
    for (let p = 1; p <= Math.min(3, totalPages); p += 1) out.push(p);
    return out;
  }, [totalPages]);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Clients</h1>
          <p className={styles.subtitle}>
            {total.toLocaleString('fr-FR').replace(/\u202f|\u00a0/g, ' ')} clients
          </p>
        </div>
        <Link to={PATHS.clientNew} className={styles.primaryBtn}>
          <span className={styles.plusIcon} aria-hidden="true">+</span>
          Nouveau client
        </Link>
      </header>

      <section className={styles.card}>
        <div className={styles.filters}>
          <input
            className={styles.input}
            placeholder="Nom ou prénom"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
          <input
            className={styles.input}
            placeholder="Ville"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
          <div className={styles.selectWrap}>
            <select className={styles.select} value={state} onChange={(e) => setState(e.target.value)}>
              {STATE_OPTIONS.map((s) => (
                <option key={s} value={s}>{s === 'Tous' ? 'État  Tous' : s}</option>
              ))}
            </select>
            <svg className={styles.selectCaret} width="10" height="6" viewBox="0 0 10 6" aria-hidden="true">
              <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </div>
          <input
            className={styles.input}
            placeholder="4 derniers chiffres"
            inputMode="numeric"
            maxLength={4}
            value={cardLast4}
            onChange={(e) => setCardLast4(e.target.value.replace(/\D/g, ''))}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
          <button type="button" className={styles.searchBtn} onClick={search}>
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
              <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.6" />
              <path d="M11 11l4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
            Rechercher
          </button>
          <button type="button" className={styles.ghostBtn} onClick={reset}>
            Réinitialiser
          </button>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th className={styles.th}>Client</th>
                <th className={styles.th}>Ville / État</th>
                <th className={styles.th}>Profession</th>
                <th className={styles.th}>Naissance</th>
                <th className={styles.th}>Carte</th>
                <th className={styles.thSort}>
                  Créée le<span className={styles.sortArrow} aria-hidden="true">↓</span>
                </th>
                <th className={styles.thAction} aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td className={styles.stateCell} colSpan={7}>Chargement des clients…</td></tr>
              ) : customers.length === 0 ? (
                <tr><td className={styles.stateCell} colSpan={7}>Aucun client ne correspond à votre recherche.</td></tr>
              ) : (
                customers.map((c) => (
                  <tr key={c.id} className={styles.row} onClick={() => navigate(PATHS.client(c.id))}>
                    <td className={styles.td}>
                      <div className={styles.client}>
                        <span className={styles.avatar}>{initials(c)}</span>
                        <span className={styles.clientName}>{c.firstName} {c.lastName}</span>
                      </div>
                    </td>
                    <td className={styles.td}>{c.city}, {c.state}</td>
                    <td className={styles.td}>{c.profession}</td>
                    <td className={styles.td}>{c.birthDate.slice(0, 10)}</td>
                    <td className={styles.td}>
                      <span className={styles.cardNumber}>
                        <span className={styles.dots} aria-hidden="true">••••</span> {c.cardLast4}
                      </span>
                    </td>
                    <td className={styles.td}>{c.createdAt.slice(0, 10)}</td>
                    <td className={styles.tdAction}>
                      <Link to={PATHS.client(c.id)} className={styles.rowBtn} onClick={(e) => e.stopPropagation()}>
                        Voir la fiche
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <footer className={styles.footer}>
          <p className={styles.footerText}>
            {first}–{last} sur {total.toLocaleString('fr-FR').replace(/\u202f|\u00a0/g, ' ')} · tri : date de création
          </p>
          <div className={styles.pagination}>
            <div className={styles.selectWrap}>
              <select
                className={styles.pageSelect}
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
              >
                <option value={10}>10 / page</option>
                <option value={25}>25 / page</option>
                <option value={50}>50 / page</option>
              </select>
              <svg className={styles.selectCaret} width="10" height="6" viewBox="0 0 10 6" aria-hidden="true">
                <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              </svg>
            </div>
            <button type="button" className={styles.pageBtn} onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>‹</button>
            {pageButtons.map((p) => (
              <button
                key={p}
                type="button"
                className={`${styles.pageBtn} ${p === page ? styles.pageBtnActive : ''}`}
                onClick={() => setPage(p)}
              >
                {p}
              </button>
            ))}
            <span className={styles.ellipsis}>…</span>
            <button type="button" className={styles.pageBtn} onClick={() => setPage(totalPages)}>{totalPages}</button>
            <button type="button" className={styles.pageBtn} onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>›</button>
          </div>
        </footer>
      </section>
    </div>
  );
}