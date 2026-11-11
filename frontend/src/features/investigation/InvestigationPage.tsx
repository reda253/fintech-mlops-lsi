import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { transactionsApi } from '@/api/transactions';
import { MOCK_TRANSACTIONS_LIST } from '@/features/transactions/mockTransactions';
import type { FullTransactionStatus, TransactionItem } from '@/types/transaction';
import styles from './InvestigationPage.module.css';

type TabKey = 'overview' | 'client' | 'ml' | 'history' | 'decision';

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: 'Vue générale' },
  { key: 'client', label: 'Client' },
  { key: 'ml', label: 'Analyse ML' },
  { key: 'history', label: 'Historique' },
  { key: 'decision', label: 'Décision' },
];

interface OtherTx {
  date: string;
  amount: string;
  category: string;
  status: FullTransactionStatus;
}

interface ContextMeta {
  distanceKm: number;
  amountRatio: string;
  mlLatencyMs: number | null;
  otherTransactions: OtherTx[];
  timeline: Array<{ title: string; date: string; highlight?: boolean }>;
}

interface SavedDecision {
  choice: 'APPROUVER' | 'BLOQUER';
  finalStatus: FullTransactionStatus;
  comment: string;
  author: string;
  decidedAt: string;
  reviewId: string;
}

const CONTEXT_BY_TX: Record<string, ContextMeta> = {
  'tx-bfc6490f': {
    distanceKm: 763,
    amountRatio: '× 4.1',
    mlLatencyMs: 14,
    otherTransactions: [
      { date: '09 oct. 12:58', amount: '439,26 USD', category: 'gas_transport', status: 'EN_REVUE' },
      { date: '09 oct. 11:19', amount: '65,85 USD', category: 'personal_care', status: 'APPROUVEE' },
      { date: '09 oct. 09:58', amount: '92,59 USD', category: 'misc_pos', status: 'APPROUVEE' },
    ],
    timeline: [
      { title: 'Transaction enregistrée (EN_ATTENTE)', date: '09 oct. 14:17' },
      { title: 'Évaluation du risque : REVUE', date: '09 oct. 14:18' },
      { title: 'Revue ouverte rv_a8d6e', date: '09 oct. 14:19', highlight: true },
    ],
  },
  'tx-bd658318': {
    distanceKm: 948,
    amountRatio: '× 8.3',
    mlLatencyMs: null,
    otherTransactions: [
      { date: '09 oct. 12:04', amount: '59,68 USD', category: 'misc_net', status: 'APPROUVEE' },
      { date: '09 oct. 10:34', amount: '31,91 USD', category: 'gas_transport', status: 'APPROUVEE' },
      { date: '09 oct. 09:04', amount: '67,49 USD', category: 'kids_pets', status: 'APPROUVEE' },
    ],
    timeline: [
      { title: 'Transaction enregistrée (EN_ATTENTE)', date: '09 oct. 13:32' },
      { title: 'Évaluation du risque : REVUE', date: '09 oct. 13:33' },
      { title: 'Revue ouverte rv_7abd2', date: '09 oct. 13:34', highlight: true },
    ],
  },
  'tx-613b9873': {
    distanceKm: 412,
    amountRatio: '× 5.8',
    mlLatencyMs: 12,
    otherTransactions: [
      { date: '09 oct. 14:10', amount: '555,44 USD', category: 'grocery_pos', status: 'EN_REVUE' },
      { date: '09 oct. 13:43', amount: '209,74 USD', category: 'shopping_net', status: 'EN_REVUE' },
      { date: '09 oct. 12:55', amount: '126,66 USD', category: 'shopping_net', status: 'APPROUVEE' },
    ],
    timeline: [
      { title: 'Transaction enregistrée (EN_ATTENTE)', date: '09 oct. 14:27' },
      { title: 'Évaluation du risque : BLOQUER', date: '09 oct. 14:28' },
      { title: 'Blocage automatique appliqué', date: '09 oct. 14:28', highlight: true },
    ],
  },
};

function formatDateTime(iso: string) {
  const d = new Date(iso);
  const day = String(d.getUTCDate()).padStart(2, '0');
  const months = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
  return `${day} ${months[d.getUTCMonth()]} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

function formatMoney(n: number) {
  return `${n.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace(/\u202f|\u00a0/g, '')} USD`;
}

function shortRef(transNum: string) {
  return `${transNum.slice(0, 8)}...`;
}

function formatPredictionSet(set: number[] | null | undefined) {
  if (!set) return '—';
  if (set.length === 0) return '[]';
  return `[${set.join(',')}]`;
}

function StatusPill({ status }: { status: FullTransactionStatus | 'TRAITEE' }) {
  const cls =
    status === 'APPROUVEE' || status === 'TRAITEE'
      ? styles.pillApproved
      : status === 'BLOQUEE'
        ? styles.pillBlocked
        : status === 'EN_REVUE'
          ? styles.pillReview
          : styles.pillNeutral;
  return <span className={`${styles.pill} ${cls}`}>{status}</span>;
}

function ReasonPill({ reason }: { reason: string }) {
  const cls =
    reason === 'ML_INDISPONIBLE' || reason === 'CLIENT_INDISPONIBLE'
      ? styles.pillBlocked
      : reason === 'MODELE_INCERTAIN'
        ? styles.pillReview
        : styles.pillNeutral;
  return <span className={`${styles.pill} ${cls}`}>{reason}</span>;
}

function GaugeArc({
  value,
  subText,
}: {
  value: number | null;
  subText?: string;
}) {
  const radius = 76;
  const circumference = Math.PI * radius;
  const pct = value !== null && value !== undefined ? Math.max(0, Math.min(1, value)) : 0;
  const dashOffset = circumference * (1 - pct);
  const strokeColor =
    value === null || value === undefined
      ? 'transparent'
      : value >= 0.8
        ? '#e5484d'
        : value >= 0.4
          ? '#e59a3c'
          : '#56d364';

  return (
    <div className={styles.gaugeWrap}>
      <svg viewBox="0 0 200 112" className={styles.gaugeSvg} aria-hidden="true">
        <path
          d="M 24 98 A 76 76 0 0 1 176 98"
          fill="none"
          stroke="#262626"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {value !== null && value !== undefined && (
          <path
            d="M 24 98 A 76 76 0 0 1 176 98"
            fill="none"
            stroke={strokeColor}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
          />
        )}
      </svg>
      <div className={styles.gaugeCenter}>
        <span className={styles.gaugeValue}>
          {value !== null && value !== undefined ? value.toFixed(2).replace('.', ',') : '—'}
        </span>
        <span className={styles.gaugeCaption}>
          {value !== null && value !== undefined ? 'Probabilité calibrée' : 'Non disponible'}
        </span>
        {subText && <span className={styles.gaugeSubCaption}>{subText}</span>}
      </div>
    </div>
  );
}

export function InvestigationPage() {
  const { transactionId } = useParams<{ transactionId?: string }>();
  const [tx, setTx] = useState<TransactionItem>(
    () =>
      MOCK_TRANSACTIONS_LIST.find((t) => t.id === transactionId || t.transNum.startsWith(transactionId ?? '')) ??
      MOCK_TRANSACTIONS_LIST[1],
  );
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  // État pour la modale de décision (maquette 10) et le résultat de revue (maquette 10b)
  const [isDecisionModalOpen, setIsDecisionModalOpen] = useState(false);
  const [decisionChoice, setDecisionChoice] = useState<'APPROUVER' | 'BLOQUER'>('BLOQUER');
  const [decisionComment, setDecisionComment] = useState(
    'Montant atypique, carte utilisée à plus de 800 km du domicile',
  );
  const [savedDecisions, setSavedDecisions] = useState<Record<string, SavedDecision>>({});
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const targetId = transactionId ?? 'tx-bfc6490f';
    (async () => {
      try {
        const res = await transactionsApi.get(targetId);
        if (alive && res) setTx(res);
      } catch {
        if (!alive) return;
        const found =
          MOCK_TRANSACTIONS_LIST.find(
            (item) => item.id === targetId || item.transNum.startsWith(targetId),
          ) ?? MOCK_TRANSACTIONS_LIST[1];
        setTx(found);
      }
    })();
    return () => {
      alive = false;
    };
  }, [transactionId]);

  const contextMeta: ContextMeta = useMemo(() => {
    if (CONTEXT_BY_TX[tx.id]) return CONTEXT_BY_TX[tx.id];
    const baseTime = formatDateTime(tx.transDateTime);
    return {
      distanceKm: 540,
      amountRatio: '× 3.4',
      mlLatencyMs: tx.risk?.reason === 'ML_INDISPONIBLE' ? null : 14,
      otherTransactions: [
        { date: '09 oct. 12:58', amount: '439,26 USD', category: 'gas_transport', status: 'EN_REVUE' },
        { date: '09 oct. 11:19', amount: '65,85 USD', category: 'personal_care', status: 'APPROUVEE' },
        { date: '09 oct. 09:58', amount: '92,59 USD', category: 'misc_pos', status: 'APPROUVEE' },
      ],
      timeline: [
        { title: 'Transaction enregistrée (EN_ATTENTE)', date: baseTime },
        { title: `Évaluation du risque : ${tx.risk?.decision ?? 'REVUE'}`, date: baseTime },
        {
          title: tx.risk?.reviewId
            ? `Revue ouverte ${tx.risk.reviewId}`
            : `Décision ${tx.status} appliquée`,
          date: baseTime,
          highlight: true,
        },
      ],
    };
  }, [tx]);

  const predKey = useMemo(() => {
    const s = tx.risk?.predictionSet;
    if (!s) return 'null';
    if (s.length === 0) return '[]';
    if (s.length === 1 && s[0] === 0) return '[0]';
    if (s.length === 1 && s[0] === 1) return '[1]';
    return '[0,1]';
  }, [tx.risk?.predictionSet]);

  const isMlUnavailable = tx.risk?.reason === 'ML_INDISPONIBLE';
  const reviewId = tx.risk?.reviewId ?? `rv_${tx.transNum.slice(0, 6)}`;
  const currentDecision = savedDecisions[tx.id];

  const handleConfirmDecision = () => {
    const finalStatus: FullTransactionStatus =
      decisionChoice === 'APPROUVER' ? 'APPROUVEE' : 'BLOQUEE';

    // Met à jour la transaction en mémoire (pour que la liste Transactions reflète aussi le changement)
    const idx = MOCK_TRANSACTIONS_LIST.findIndex((item) => item.id === tx.id);
    if (idx !== -1) {
      MOCK_TRANSACTIONS_LIST[idx] = {
        ...MOCK_TRANSACTIONS_LIST[idx],
        status: finalStatus,
        decisionSource: 'MANUELLE',
      };
    }

    setTx((prev) => ({
      ...prev,
      status: finalStatus,
      decisionSource: 'MANUELLE',
    }));

    setSavedDecisions((prev) => ({
      ...prev,
      [tx.id]: {
        choice: decisionChoice,
        finalStatus,
        comment: decisionComment.trim() || 'Décision manuelle enregistrée',
        author: 'analyste1',
        decidedAt: '09 oct. 2026 · 14:40:12',
        reviewId,
      },
    }));

    setIsDecisionModalOpen(false);
    setActiveTab('decision');
    setToastMsg('Décision enregistrée — file mise à jour');
    setTimeout(() => setToastMsg(null), 4500);
  };

  return (
    <div className={styles.page}>
      {/* ── En-tête ─────────────────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>
            {activeTab === 'decision' ? `Revue ${reviewId}` : `Transaction ${shortRef(tx.transNum)}`}
          </h1>
          <div className={styles.badges}>
            <StatusPill status={tx.status} />
            <span className={`${styles.pill} ${styles.pillNeutral}`}>
              {tx.decisionSource ?? 'AUTO'}
            </span>
            {tx.risk?.reason && <ReasonPill reason={tx.risk.reason} />}
          </div>
        </div>

        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.secondaryBtn}
            onClick={() => setActiveTab('decision')}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
              <rect x="3" y="2" width="10" height="12" rx="1.8" fill="none" stroke="currentColor" strokeWidth="1.4" />
              <path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
            Voir la revue
          </button>
          <button
            type="button"
            className={styles.primaryBtn}
            onClick={() => setIsDecisionModalOpen(true)}
          >
            Décider
          </button>
        </div>
      </header>

      {/* ── Barre d'onglets fonctionnelle + sélecteur de cas ── */}
      <div className={styles.tabsRow}>
        <div className={styles.tabsBar} role="tablist">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={activeTab === t.key}
              className={`${styles.tabBtn} ${activeTab === t.key ? styles.tabBtnActive : ''}`}
              onClick={() => setActiveTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className={styles.demoSwitcher}>
          <span className={styles.demoLabel}>Cas maquette :</span>
          <button
            type="button"
            className={`${styles.demoChip} ${tx.id === 'tx-bfc6490f' ? styles.demoChipActive : ''}`}
            onClick={() => {
              setTx(MOCK_TRANSACTIONS_LIST[1]);
              setActiveTab('overview');
            }}
          >
            08 · bfc6490f (Incertain)
          </button>
          <button
            type="button"
            className={`${styles.demoChip} ${tx.id === 'tx-bd658318' ? styles.demoChipActive : ''}`}
            onClick={() => {
              setTx(MOCK_TRANSACTIONS_LIST[6]);
              setActiveTab('overview');
            }}
          >
            08b · bd658318 (ML_INDISPONIBLE)
          </button>
          <button
            type="button"
            className={`${styles.demoChip} ${tx.id === 'tx-613b9873' ? styles.demoChipActive : ''}`}
            onClick={() => {
              setTx(MOCK_TRANSACTIONS_LIST[0]);
              setActiveTab('overview');
            }}
          >
            07 · 613b9873 (Bloquée)
          </button>
        </div>
      </div>

      {/* ── Bannière d'alerte ML_INDISPONIBLE (maquette 08b) ── */}
      {isMlUnavailable && activeTab !== 'decision' && (
        <div className={styles.mlBanner} role="alert">
          <strong>ML_INDISPONIBLE</strong> · Le modèle est indisponible. La transaction a été envoyée en revue humaine
          par sécurité (mode fail-safe) : elle n&apos;est jamais approuvée automatiquement sans avis du modèle.
          Probabilité, incertitude et ensemble de prédiction ne sont pas disponibles.
        </div>
      )}

      {/* ======================================================
          ONGLET 5 : DÉCISION / VOIR LA REVUE (Maquette 10b)
         ====================================================== */}
      {activeTab === 'decision' && (
        <div className={styles.decisionResultWrap}>
          <div className={styles.successBanner}>
            <strong>{currentDecision ? 'Décision enregistrée.' : 'Dossier de revue.'}</strong>{' '}
            {currentDecision
              ? 'La revue est passée à TRAITEE et la transaction a reçu son statut final. La file de revue a été mise à jour (37 revues ouvertes).'
              : 'Cette transaction est associée à une revue humaine. Cliquez sur « Décider » en haut à droite pour enregistrer une décision.'}
          </div>

          <div className={styles.decisionGrid}>
            <section className={styles.card}>
              <div className={styles.cardHeader}>
                <h2 className={styles.cardTitle}>Résultat</h2>
              </div>
              <dl className={styles.kvList}>
                <div className={styles.kvRow}>
                  <dt>Statut de la revue</dt>
                  <dd>
                    <StatusPill status={currentDecision ? 'TRAITEE' : 'EN_REVUE'} />
                  </dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Statut final de la transaction</dt>
                  <dd>
                    <StatusPill status={currentDecision ? currentDecision.finalStatus : tx.status} />
                  </dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Origine de la décision</dt>
                  <dd>{currentDecision ? 'MANUELLE' : tx.decisionSource ?? 'AUTO'}</dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Auteur</dt>
                  <dd>{currentDecision ? currentDecision.author : 'analyste1'}</dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Date et heure</dt>
                  <dd>{currentDecision ? currentDecision.decidedAt : formatDateTime(tx.transDateTime)}</dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Commentaire</dt>
                  <dd>
                    {currentDecision
                      ? currentDecision.comment
                      : decisionComment}
                  </dd>
                </div>
              </dl>
            </section>

            <section className={styles.card}>
              <div className={styles.cardHeader}>
                <h2 className={styles.cardTitle}>Évaluation initiale du modèle</h2>
              </div>
              <dl className={styles.kvList}>
                <div className={styles.kvRow}>
                  <dt>Décision automatique</dt>
                  <dd>{tx.risk?.decision ?? 'REVUE'}</dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Raison</dt>
                  <dd>
                    {tx.risk?.reason ? <ReasonPill reason={tx.risk.reason} /> : '—'}
                  </dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Probabilité</dt>
                  <dd>
                    {tx.risk?.fraudProbability !== null && tx.risk?.fraudProbability !== undefined
                      ? tx.risk.fraudProbability.toFixed(2).replace('.', ',')
                      : '—'}
                  </dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Ensemble</dt>
                  <dd>
                    <span className={`${styles.setTag} ${styles.setTagAmber}`}>
                      {formatPredictionSet(tx.risk?.predictionSet)}
                    </span>
                  </dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Incertitude</dt>
                  <dd>
                    {tx.risk?.uncertainty !== null && tx.risk?.uncertainty !== undefined
                      ? `${tx.risk.uncertainty.toFixed(2).replace('.', ',')} ${tx.risk.uncertaintyLevel ?? ''}`
                      : '—'}
                  </dd>
                </div>
                <div className={styles.kvRow}>
                  <dt>Modèle</dt>
                  <dd>{tx.risk?.modelVersion ?? '—'}</dd>
                </div>
              </dl>
            </section>
          </div>

          <section className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Chronologie</h2>
            </div>
            <ul className={styles.timeline}>
              <li className={styles.timelineItem}>
                <span className={styles.timelineDot} />
                <div>
                  <p className={styles.timelineTitle}>Revue ouverte</p>
                  <p className={styles.timelineDate}>● {formatDateTime(tx.transDateTime)}</p>
                </div>
              </li>
              <li className={styles.timelineItem}>
                <span className={`${styles.timelineDot} ${styles.timelineDotRed}`} />
                <div>
                  <p className={styles.timelineTitle}>
                    Décision {currentDecision?.choice ?? 'BLOQUER'} enregistrée par analyste1
                  </p>
                  <p className={styles.timelineDate}>● 09 oct. 14:40</p>
                </div>
              </li>
              <li className={styles.timelineItem}>
                <span className={styles.timelineDot} />
                <div>
                  <p className={styles.timelineTitle}>
                    Transaction passée à {currentDecision?.finalStatus ?? tx.status} (MANUELLE)
                  </p>
                  <p className={styles.timelineDate}>● 09 oct. 14:40</p>
                </div>
              </li>
            </ul>
          </section>
        </div>
      )}

      {/* ======================================================
          ONGLETS : VUE GÉNÉRALE / CLIENT / ANALYSE ML / HISTORIQUE
         ====================================================== */}
      {activeTab !== 'decision' && (
        <>
          {(activeTab === 'overview' || activeTab === 'ml' || activeTab === 'client') && (
            <div className={styles.threeColGrid}>
              {/* Colonne 1 : Probabilité de fraude + Incertitude */}
              {(activeTab === 'overview' || activeTab === 'ml') && (
                <div className={styles.colStack}>
                  <section className={styles.card}>
                    <div className={styles.cardHeader}>
                      <h2 className={styles.cardTitle}>Probabilité de fraude</h2>
                      <span className={styles.cardHint}>calibrée</span>
                    </div>
                    <GaugeArc value={tx.risk?.fraudProbability ?? null} />
                  </section>

                  <section className={styles.card}>
                    <div className={styles.cardHeader}>
                      <h2 className={styles.cardTitle}>Incertitude</h2>
                    </div>
                    {tx.risk?.uncertainty !== null && tx.risk?.uncertainty !== undefined ? (
                      <div className={styles.uncertaintyBody}>
                        <div className={styles.uncertaintyTop}>
                          <span className={styles.uncertaintyVal}>
                            {tx.risk.uncertainty.toFixed(2).replace('.', ',')}
                          </span>
                          <span
                            className={`${styles.pill} ${
                              tx.risk.uncertaintyLevel === 'ELEVEE' ? styles.pillReview : styles.pillNeutral
                            }`}
                          >
                            {tx.risk.uncertaintyLevel ?? 'FAIBLE'}
                          </span>
                        </div>
                        <div className={styles.uncertaintyBar}>
                          <div
                            className={styles.uncertaintyFill}
                            style={{
                              width: `${Math.min(100, Math.max(8, Math.round(tx.risk.uncertainty * 100)))}%`,
                              background: tx.risk.uncertaintyLevel === 'ELEVEE' ? '#d99b26' : '#525252',
                            }}
                          />
                        </div>
                        <p className={styles.uncertaintyMeta}>
                          Niveau {tx.risk.uncertaintyLevel ?? 'FAIBLE'} · α = 0,05
                        </p>
                      </div>
                    ) : (
                      <p className={styles.unavailableText}>
                        Non disponible ({tx.risk?.reason ?? 'ML_INDISPONIBLE'})
                      </p>
                    )}
                  </section>
                </div>
              )}

              {/* Colonne 2 : Informations de transaction + Décision du système */}
              <div className={styles.colStack}>
                <section className={styles.card}>
                  <div className={styles.cardHeader}>
                    <h2 className={styles.cardTitle}>Informations de transaction</h2>
                  </div>
                  <dl className={styles.kvList}>
                    <div className={styles.kvRow}>
                      <dt>N° transaction</dt>
                      <dd className={styles.mono}>{tx.transNum}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Date</dt>
                      <dd>{formatDateTime(tx.transDateTime)}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Montant</dt>
                      <dd>{formatMoney(tx.amount)}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Catégorie</dt>
                      <dd>{tx.category}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Marchand</dt>
                      <dd>{tx.merchant}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Carte</dt>
                      <dd className={styles.mono}>•••• {tx.cardLast4}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Statut actuel</dt>
                      <dd>{tx.status}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Origine de la décision</dt>
                      <dd>{tx.decisionSource === 'MANUELLE' ? 'Manuelle' : 'Automatique'}</dd>
                    </div>
                  </dl>
                </section>

                <section className={styles.card}>
                  <div className={styles.cardHeader}>
                    <h2 className={styles.cardTitle}>Décision du système</h2>
                  </div>
                  <dl className={styles.kvList}>
                    <div className={styles.kvRow}>
                      <dt>Décision</dt>
                      <dd>{tx.risk?.decision ?? '—'}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Raison</dt>
                      <dd>{tx.risk?.reason ?? '—'}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Modèle</dt>
                      <dd>{tx.risk?.modelVersion ?? '—'}</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Latence ML</dt>
                      <dd>{contextMeta.mlLatencyMs !== null ? `${contextMeta.mlLatencyMs} ms` : '—'}</dd>
                    </div>
                  </dl>
                </section>
              </div>

              {/* Colonne 3 : Ensemble de prédiction conforme + Contexte calculé */}
              <div className={styles.colStack}>
                {(activeTab === 'overview' || activeTab === 'ml') && (
                  <section className={styles.card}>
                    <div className={styles.cardHeader}>
                      <h2 className={styles.cardTitle}>Ensemble de prédiction conforme</h2>
                      <span className={styles.cardHintRight}>
                        Cible de couverture :
                        <br />
                        95 %
                      </span>
                    </div>

                    <div className={styles.conformalList}>
                      <div
                        className={`${styles.conformalItem} ${
                          predKey === '[0]' ? styles.conformalActiveGreen : ''
                        }`}
                      >
                        <span className={`${styles.setTag} ${styles.setTagGreen}`}>[0]</span>
                        <div>
                          <div className={styles.conformalTitle}>Légitime</div>
                          <div className={styles.conformalSub}>Confiant → APPROUVER</div>
                        </div>
                      </div>

                      <div
                        className={`${styles.conformalItem} ${
                          predKey === '[1]' ? styles.conformalActiveRed : ''
                        }`}
                      >
                        <span className={`${styles.setTag} ${styles.setTagRed}`}>[1]</span>
                        <div>
                          <div className={styles.conformalTitle}>Fraude</div>
                          <div className={styles.conformalSub}>Confiant → BLOQUER</div>
                        </div>
                      </div>

                      <div
                        className={`${styles.conformalItem} ${
                          predKey === '[0,1]' ? styles.conformalActiveAmber : ''
                        }`}
                      >
                        <span className={`${styles.setTag} ${styles.setTagAmber}`}>[0,1]</span>
                        <div>
                          <div className={styles.conformalTitle}>Incertain</div>
                          <div className={styles.conformalSub}>
                            Les deux classes restent plausibles → REVUE
                          </div>
                        </div>
                      </div>

                      <div
                        className={`${styles.conformalItem} ${
                          predKey === '[]' ? styles.conformalActiveAmber : ''
                        }`}
                      >
                        <span className={`${styles.setTag} ${styles.setTagAmber}`}>[]</span>
                        <div>
                          <div className={styles.conformalTitle}>Aucune classe plausible</div>
                          <div className={styles.conformalSub}>Données atypiques → REVUE</div>
                        </div>
                      </div>
                    </div>

                    <p className={styles.conformalNote}>
                      {predKey === 'null'
                        ? "Aucun ensemble : le modèle n'a pas répondu."
                        : "L'ensemble liste les classes plausibles ; ce n'est pas une probabilité. La probabilité de fraude est affichée séparément."}
                    </p>
                    <p className={styles.conformalNote}>
                      Cible de couverture de la méthode conforme (1 − α), valable sous ses hypothèses : ce
                      n&apos;est pas une certitude à 95 % pour cette transaction.
                    </p>
                  </section>
                )}

                <section className={styles.card}>
                  <div className={styles.cardHeader}>
                    <h2 className={styles.cardTitle}>Contexte calculé</h2>
                    <span className={styles.cardHint}>hors modèle</span>
                  </div>
                  <dl className={styles.kvList}>
                    <div className={styles.kvRow}>
                      <dt>Client</dt>
                      <dd>
                        <Link to={`/clients/${tx.customerId}`} className={styles.clientLink}>
                          {tx.customerFirstName} {tx.customerLastName}
                        </Link>
                      </dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Distance domicile–marchand</dt>
                      <dd>{contextMeta.distanceKm} km</dd>
                    </div>
                    <div className={styles.kvRow}>
                      <dt>Montant vs moyenne du client</dt>
                      <dd>{contextMeta.amountRatio}</dd>
                    </div>
                  </dl>
                </section>
              </div>
            </div>
          )}

          {/* Grille inférieure : Autres transactions + Chronologie */}
          {(activeTab === 'overview' || activeTab === 'client' || activeTab === 'history') && (
            <div className={styles.bottomGrid}>
              <section className={styles.card}>
                <div className={styles.cardHeader}>
                  <h2 className={styles.cardTitle}>Autres transactions du client</h2>
                </div>
                <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th className={styles.th}>Date</th>
                        <th className={styles.th}>Montant</th>
                        <th className={styles.th}>Catégorie</th>
                        <th className={styles.th}>Statut</th>
                      </tr>
                    </thead>
                    <tbody>
                      {contextMeta.otherTransactions.map((ot, idx) => (
                        <tr key={idx}>
                          <td className={styles.tdDate}>{ot.date}</td>
                          <td className={styles.tdAmount}>{ot.amount}</td>
                          <td className={styles.td}>{ot.category}</td>
                          <td className={styles.td}>
                            <StatusPill status={ot.status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className={styles.card}>
                <div className={styles.cardHeader}>
                  <h2 className={styles.cardTitle}>Chronologie</h2>
                </div>
                <ul className={styles.timeline}>
                  {contextMeta.timeline.map((step, i) => (
                    <li key={i} className={styles.timelineItem}>
                      <span
                        className={`${styles.timelineDot} ${step.highlight ? styles.timelineDotRed : ''}`}
                      />
                      <div>
                        <p className={styles.timelineTitle}>{step.title}</p>
                        <p className={styles.timelineDate}>● {step.date}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          )}
        </>
      )}

      {/* ======================================================
          MODALE : DÉCISION DE REVUE (Maquette 10_ANALYSTE_decision_humaine)
         ====================================================== */}
      {isDecisionModalOpen && (
        <div
          className={styles.modalBackdrop}
          role="dialog"
          aria-modal="true"
          aria-label={`Décision de revue · ${reviewId}`}
        >
          <div className={styles.modalCard}>
            <div className={styles.modalHeader}>
              <h2 className={styles.modalTitle}>Décision de revue · {reviewId}</h2>
              <button
                type="button"
                className={styles.modalCloseBtn}
                onClick={() => setIsDecisionModalOpen(false)}
                aria-label="Fermer"
              >
                ✕
              </button>
            </div>

            <div className={styles.modalSummaryGrid}>
              <div className={styles.modalInnerCard}>
                <dl className={styles.kvList}>
                  <div className={styles.kvRow}>
                    <dt>Transaction</dt>
                    <dd className={styles.mono}>{shortRef(tx.transNum)}</dd>
                  </div>
                  <div className={styles.kvRow}>
                    <dt>Montant</dt>
                    <dd>{formatMoney(tx.amount)}</dd>
                  </div>
                  <div className={styles.kvRow}>
                    <dt>Catégorie</dt>
                    <dd>{tx.category}</dd>
                  </div>
                  <div className={styles.kvRow}>
                    <dt>Ensemble</dt>
                    <dd>
                      <span className={`${styles.setTag} ${styles.setTagAmber}`}>
                        {formatPredictionSet(tx.risk?.predictionSet)}
                      </span>
                    </dd>
                  </div>
                </dl>
              </div>

              <div className={styles.modalInnerCard}>
                <GaugeArc
                  value={tx.risk?.fraudProbability ?? null}
                  subText={
                    tx.risk?.uncertainty !== null && tx.risk?.uncertainty !== undefined
                      ? `Incertitude ${tx.risk.uncertainty.toFixed(2).replace('.', ',')} · ${tx.risk.uncertaintyLevel ?? 'FAIBLE'}`
                      : 'Incertitude non disponible'
                  }
                />
              </div>
            </div>

            <div className={styles.choiceButtonsRow}>
              <button
                type="button"
                className={`${styles.choiceApproveBtn} ${
                  decisionChoice === 'APPROUVER' ? styles.choiceSelected : ''
                }`}
                onClick={() => setDecisionChoice('APPROUVER')}
              >
                APPROUVER
              </button>
              <button
                type="button"
                className={`${styles.choiceBlockBtn} ${
                  decisionChoice === 'BLOQUER' ? styles.choiceSelected : ''
                }`}
                onClick={() => setDecisionChoice('BLOQUER')}
              >
                BLOQUER
              </button>
            </div>

            <div className={styles.commentGroup}>
              <label className={styles.commentLabel} htmlFor="decision-comment">
                Commentaire (optionnel · max. 1000 caractères)
              </label>
              <textarea
                id="decision-comment"
                className={styles.commentTextarea}
                maxLength={1000}
                rows={3}
                value={decisionComment}
                onChange={(e) => setDecisionComment(e.target.value)}
              />
              <span className={styles.charCount}>{decisionComment.length} / 1000</span>
            </div>

            <div
              className={`${styles.confirmWarningBox} ${
                decisionChoice === 'APPROUVER' ? styles.confirmBoxGreen : styles.confirmBoxRed
              }`}
            >
              <strong>Confirmer : {decisionChoice}</strong>
              <p>
                Action irréversible : la revue passera à TRAITEE et la transaction recevra son statut
                final (MANUELLE). Version de la revue : 2 (verrou optimiste). L&apos;action est tracée
                dans l&apos;audit.
              </p>
            </div>

            <div className={styles.modalFooter}>
              <button
                type="button"
                className={styles.modalCancelBtn}
                onClick={() => setIsDecisionModalOpen(false)}
              >
                Annuler
              </button>
              <button
                type="button"
                className={styles.modalConfirmBtn}
                onClick={handleConfirmDecision}
              >
                Confirmer la décision
              </button>
            </div>
          </div>
        </div>
      )}

      {toastMsg && <div className={styles.toast}>{toastMsg}</div>}
    </div>
  );
}
