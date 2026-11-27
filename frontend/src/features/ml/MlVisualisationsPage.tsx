import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { PATHS } from '@/app/router/paths';
import {
  fetchMlProjection,
  generateDeterministicProjectionPoints,
} from '@/api/ml';
import type {
  MlProjectionMethod,
  MlProjectionPoint,
  MlProjectionResponse,
  MlProjectionView,
} from '@/types/ml';
import styles from './MlVisualisationsPage.module.css';

const METHODS: Array<{ id: MlProjectionMethod; label: string }> = [
  { id: 'pca', label: 'PCA' },
  { id: 'tsne', label: 't-SNE' },
  { id: 'umap', label: 'UMAP' },
];

const VIEWS: MlProjectionView[] = ['class', 'cluster', 'outlier', 'error', 'uncertainty'];

function getMethodLabel(method: MlProjectionMethod): string {
  if (method === 'pca') return 'PCA';
  if (method === 'tsne') return 't-SNE';
  return 'UMAP';
}

function getPointColor(point: MlProjectionPoint, view: MlProjectionView): string {
  if (point.is_fraud === 1) {
    return '#ef4444'; // Red for fraud
  }
  if (view === 'uncertainty') {
    return point.label === 'ELEVEE' ? '#f59e0b' : '#9ca3af';
  }
  if (view === 'outlier') {
    return point.label === 'ANOMALIE' ? '#f59e0b' : '#9ca3af';
  }
  if (view === 'error') {
    return point.label === 'FP' || point.label === 'FN' ? '#f59e0b' : '#9ca3af';
  }
  if (view === 'cluster') {
    if (point.label === 'CLUSTER_2') return '#f59e0b';
    if (point.label === 'CLUSTER_3') return '#34d399';
    return '#9ca3af';
  }
  return '#9ca3af';
}

function formatCoordFr(val: number): string {
  return val.toFixed(1).replace('.', ',');
}

function mapCoordToSvg(value: number, min: number, max: number, size: number, pad = 28): number {
  const span = Math.max(1, max - min);
  return pad + ((value - min) / span) * (size - pad * 2);
}

export function MlVisualisationsPage() {
  const [method, setMethod] = useState<MlProjectionMethod>('tsne');
  const [view, setView] = useState<MlProjectionView>('uncertainty');
  const [fraudFilter, setFraudFilter] = useState<'all' | 0 | 1>('all');
  const [simulatedState, setSimulatedState] = useState<'normal' | 'loading' | 'unavailable'>('normal');

  const initialPoints = useMemo(
    () => generateDeterministicProjectionPoints('tsne', 'uncertainty'),
    [],
  );

  const [projection, setProjection] = useState<MlProjectionResponse>({
    method: 'tsne',
    view: 'uncertainty',
    model_version: '8',
    warning:
      "Avec t-SNE et UMAP, les distances entre groupes et la taille des groupes n'ont pas de signification quantitative : seule la proximité locale est interprétable. Projection calculée pour la version 8 du modèle.",
    sample_size_label: '~20 000 points',
    points: initialPoints,
  });

  const [selectedPoint, setSelectedPoint] = useState<MlProjectionPoint | null>(
    () => initialPoints[0] ?? null,
  );

  useEffect(() => {
    let active = true;
    fetchMlProjection(method, view)
      .then((res) => {
        if (!active) return;
        setProjection(res);
        const firstPt = res.points[0] ?? null;
        setSelectedPoint(firstPt);
      })
      .catch(() => {
        // Keep deterministic points
      });
    return () => {
      active = false;
    };
  }, [method, view]);

  const visiblePoints = useMemo(() => {
    if (fraudFilter === 'all') return projection.points;
    return projection.points.filter((pt) => pt.is_fraud === fraudFilter);
  }, [projection.points, fraudFilter]);

  const pcaPreviewPoints = useMemo(
    () => generateDeterministicProjectionPoints('pca', view),
    [view],
  );
  const tsnePreviewPoints = useMemo(
    () => generateDeterministicProjectionPoints('tsne', view),
    [view],
  );
  const umapPreviewPoints = useMemo(
    () => generateDeterministicProjectionPoints('umap', view),
    [view],
  );

  const activePoint: MlProjectionPoint = selectedPoint ?? {
    id: 'fallback-point',
    x: 12.4,
    y: -3.1,
    label: 'ELEVEE',
    is_fraud: 0,
  };

  const toggleFraudFilter = (target: 0 | 1) => {
    setFraudFilter((prev) => (prev === target ? 'all' : target));
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Intelligence ML</h1>
          <p className={styles.subtitle}>
            Projections des transactions de la zone de test · <code>GET /api/v1/ml/viz/{'{méthode}'}</code>
          </p>
        </div>
        <div className={styles.headerActions}>
          <Link to={PATHS.ml} className={styles.perfNavBtn}>
            ← Performances &amp; incertitude
          </Link>
        </div>
      </header>

      {/* Method & View controls */}
      <div className={styles.controlsRow}>
        <div className={styles.segmentedGroup} role="group" aria-label="Méthode de projection">
          {METHODS.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`${styles.segBtn} ${method === m.id ? styles.segBtnActive : ''}`}
              onClick={() => {
                setMethod(m.id);
                setSimulatedState('normal');
              }}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className={styles.segmentedGroup} role="group" aria-label="Vue de coloration">
          {VIEWS.map((v) => (
            <button
              key={v}
              type="button"
              className={`${styles.segBtn} ${view === v ? styles.segBtnActive : ''}`}
              onClick={() => {
                setView(v);
                setSimulatedState('normal');
              }}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* Mandatory §4.11 Warning Banner */}
      <div className={styles.warningBanner} role="alert">
        <strong>Interprétation.</strong> Avec t-SNE et UMAP, les distances entre groupes et la taille des
        groupes n&apos;ont pas de signification quantitative : seule la proximité locale est interprétable.
        Projection calculée pour la version {projection.model_version} du modèle.
      </div>

      {/* Main Row: Scatter Plot + Right Sidebar (Légende/filtres & Informations) */}
      <section className={styles.mainGrid}>
        <article className={styles.card}>
          <div className={styles.cardHeaderSplit}>
            <h2 className={styles.cardTitle}>
              Projection {getMethodLabel(method)} · vue « {view} »
            </h2>
            <div className={styles.inlineLegend}>
              <span className={styles.legendItem}>
                <i className={styles.dotLow} /> Incertitude FAIBLE
              </span>
              <span className={styles.legendItem}>
                <i className={styles.dotHigh} /> Incertitude ÉLEVÉE
              </span>
              <span className={styles.legendItem}>
                <i className={styles.dotFraud} /> Fraude (is_fraud = 1)
              </span>
            </div>
          </div>

          <div className={styles.scatterContainer}>
            {simulatedState === 'loading' ? (
              <div className={styles.mainLoadingState}>
                <div className={styles.skeletonPulse} />
                <p className={styles.stateHintText}>
                  Chargement de la projection {getMethodLabel(method)} (~20 000 points)…
                </p>
              </div>
            ) : simulatedState === 'unavailable' ? (
              <div className={styles.mainUnavailableState}>
                <span className={styles.unavailableIcon}>⌸</span>
                <p className={styles.unavailableTitle}>Projection indisponible</p>
                <p className={styles.unavailableSub}>
                  Le ml-service ne répond pas (503). Réessayez plus tard.
                </p>
                <button
                  type="button"
                  className={styles.stateToggleBtn}
                  onClick={() => setSimulatedState('normal')}
                >
                  Réessayer maintenant
                </button>
              </div>
            ) : (
              <>
                <svg
                  viewBox="0 0 800 340"
                  className={styles.scatterSvg}
                  role="img"
                  aria-label={`Projection ${getMethodLabel(method)} vue ${view}`}
                >
                  {/* Grid lines */}
                  <line x1="200" y1="0" x2="200" y2="340" className={styles.gridLine} />
                  <line x1="400" y1="0" x2="400" y2="340" className={styles.gridLine} />
                  <line x1="600" y1="0" x2="600" y2="340" className={styles.gridLine} />
                  <line x1="0" y1="85" x2="800" y2="85" className={styles.gridLine} />
                  <line x1="0" y1="170" x2="800" y2="170" className={styles.gridLine} />
                  <line x1="0" y1="255" x2="800" y2="255" className={styles.gridLine} />

                  {visiblePoints.map((pt) => {
                    const cx = mapCoordToSvg(pt.x, -26, 26, 800, 44);
                    const cy = mapCoordToSvg(-pt.y, -22, 22, 340, 28);
                    const isSelected = pt.id === activePoint.id;
                    return (
                      <g key={pt.id}>
                        {isSelected && (
                          <circle
                            cx={cx}
                            cy={cy}
                            r={8}
                            fill="none"
                            stroke="#f59e0b"
                            strokeWidth="1.5"
                          />
                        )}
                        <circle
                          cx={cx}
                          cy={cy}
                          r={isSelected ? 4.2 : 2.8}
                          fill={getPointColor(pt, view)}
                          fillOpacity={0.92}
                          className={styles.scatterPoint}
                          onClick={() => setSelectedPoint(pt)}
                        />
                      </g>
                    );
                  })}
                </svg>

                {/* Floating selected point tooltip matching Mockup 12 */}
                <div className={styles.floatingTooltip} aria-live="polite">
                  <p className={styles.tooltipTitle}>Point sélectionné</p>
                  <p className={styles.tooltipLine}>label : {activePoint.label}</p>
                  <p className={styles.tooltipLine}>is_fraud : {activePoint.is_fraud}</p>
                  <p className={styles.tooltipLine}>
                    x {formatCoordFr(activePoint.x)} · y {formatCoordFr(activePoint.y)}
                  </p>
                </div>
              </>
            )}
          </div>
        </article>

        <div className={styles.sideColumn}>
          <article className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Légende et filtres</h2>
            </div>

            <div className={styles.filterPills}>
              <button
                type="button"
                className={`${styles.filterPill} ${fraudFilter === 0 ? styles.filterPillActive : ''}`}
                onClick={() => toggleFraudFilter(0)}
              >
                is_fraud = 0
              </button>
              <button
                type="button"
                className={`${styles.filterPill} ${fraudFilter === 1 ? styles.filterPillActive : ''}`}
                onClick={() => toggleFraudFilter(1)}
              >
                is_fraud = 1
              </button>
            </div>

            <div className={styles.sideLegendList}>
              <div className={styles.sideLegendRow}>
                <span className={styles.legendItem}>
                  <i className={styles.dotLow} /> Incertitude FAIBLE
                </span>
                <span className={styles.legendItem}>
                  <i className={styles.dotHigh} /> Incertitude ÉLEVÉE
                </span>
              </div>
              <div className={styles.sideLegendRow}>
                <span className={styles.legendItem}>
                  <i className={styles.dotFraud} /> Fraude (is_fraud = 1)
                </span>
              </div>
            </div>
          </article>

          <article className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Informations</h2>
            </div>

            <dl className={styles.kvList}>
              <div className={styles.kvRow}>
                <dt>Méthode</dt>
                <dd>{getMethodLabel(method)}</dd>
              </div>
              <div className={styles.kvRow}>
                <dt>Vue</dt>
                <dd>{view}</dd>
              </div>
              <div className={styles.kvRow}>
                <dt>Version du modèle</dt>
                <dd>{projection.model_version}</dd>
              </div>
              <div className={styles.kvRow}>
                <dt>Échantillon</dt>
                <dd>{projection.sample_size_label}</dd>
              </div>
            </dl>
          </article>
        </div>
      </section>

      {/* Middle Row: 3 Mini 2D Previews (PCA · 2D, t-SNE · 2D, UMAP · 2D) */}
      <section className={styles.threeColGrid}>
        {(
          [
            { id: 'pca' as const, title: 'PCA · 2D', pts: pcaPreviewPoints },
            { id: 'tsne' as const, title: 't-SNE · 2D', pts: tsnePreviewPoints },
            { id: 'umap' as const, title: 'UMAP · 2D', pts: umapPreviewPoints },
          ] as const
        ).map((mini) => (
          <article
            key={mini.id}
            className={`${styles.card} ${styles.miniCard} ${
              method === mini.id ? styles.miniCardActive : ''
            }`}
            onClick={() => {
              setMethod(mini.id);
              setSimulatedState('normal');
            }}
          >
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>{mini.title}</h2>
            </div>

            <svg viewBox="0 0 380 165" className={styles.miniSvg} aria-label={mini.title}>
              <line x1="126" y1="0" x2="126" y2="165" className={styles.gridLine} />
              <line x1="254" y1="0" x2="254" y2="165" className={styles.gridLine} />
              <line x1="0" y1="55" x2="380" y2="55" className={styles.gridLine} />
              <line x1="0" y1="110" x2="380" y2="110" className={styles.gridLine} />
              {mini.pts.map((pt) => {
                const cx = mapCoordToSvg(pt.x, -26, 26, 380, 24);
                const cy = mapCoordToSvg(-pt.y, -22, 22, 165, 16);
                return (
                  <circle
                    key={pt.id}
                    cx={cx}
                    cy={cy}
                    r={pt.is_fraud === 1 ? 2.4 : 2.0}
                    fill={getPointColor(pt, view)}
                    fillOpacity={0.9}
                  />
                );
              })}
            </svg>
          </article>
        ))}
      </section>

      {/* Bottom Row: État chargement + État données indisponibles + Tooltip des points */}
      <section className={styles.threeColGrid}>
        <article className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>État : chargement</h2>
            <button
              type="button"
              className={styles.stateToggleBtn}
              onClick={() =>
                setSimulatedState((s) => (s === 'loading' ? 'normal' : 'loading'))
              }
            >
              {simulatedState === 'loading' ? 'Rétablir' : 'Tester'}
            </button>
          </div>
          <div className={styles.skeletonBlock} aria-label="Aperçu de l’état de chargement">
            <div className={styles.skeletonShimmerBar} />
            <div className={styles.skeletonShimmerSub} />
            <span className={styles.skeletonCaption}>
              Skeleton affiché pendant le calcul / téléchargement du nuage de points
            </span>
          </div>
        </article>

        <article className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>État : données indisponibles</h2>
            <button
              type="button"
              className={styles.stateToggleBtn}
              onClick={() =>
                setSimulatedState((s) => (s === 'unavailable' ? 'normal' : 'unavailable'))
              }
            >
              {simulatedState === 'unavailable' ? 'Rétablir' : 'Tester 503'}
            </button>
          </div>
          <div className={styles.unavailableBox}>
            <span className={styles.unavailableIcon} aria-hidden="true">
              ⌸
            </span>
            <p className={styles.unavailableTitle}>Projection indisponible</p>
            <p className={styles.unavailableSub}>
              Le ml-service ne répond pas (503). Réessayez plus tard.
            </p>
          </div>
        </article>

        <article className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Tooltip des points</h2>
          </div>

          <dl className={styles.kvList}>
            <div className={styles.kvRow}>
              <dt>label</dt>
              <dd className={styles.monoValue}>{activePoint.label}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>is_fraud</dt>
              <dd className={styles.monoValue}>{activePoint.is_fraud}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>x / y</dt>
              <dd className={styles.monoValue}>
                {formatCoordFr(activePoint.x)} / {formatCoordFr(activePoint.y)}
              </dd>
            </div>
          </dl>
        </article>
      </section>
    </div>
  );
}
