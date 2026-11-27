import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { PATHS } from '@/app/router/paths';
import { DEFAULT_PERFORMANCE_REPORT, fetchMlPerformanceReport } from '@/api/ml';
import type { MlPerformanceReport } from '@/types/ml';
import styles from './MlPerformancePage.module.css';

type PerformanceTab = 'overview' | 'comparison' | 'calibration' | 'uncertainty';

function formatDecimalFr(value: number, digits = 3): string {
  return value.toFixed(digits).replace('.', ',');
}

function formatPctFr(value: number, digits = 1): string {
  return `${value.toFixed(digits).replace('.', ',')} %`;
}

function formatNumberFr(value: number): string {
  return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

export function MlPerformancePage() {
  const [report, setReport] = useState<MlPerformanceReport>(DEFAULT_PERFORMANCE_REPORT);
  const [activeTab, setActiveTab] = useState<PerformanceTab>('overview');

  useEffect(() => {
    let active = true;
    fetchMlPerformanceReport()
      .then((res) => {
        if (active) setReport(res);
      })
      .catch(() => {
        // Keep deterministic mockup report
      });
    return () => {
      active = false;
    };
  }, []);

  const trainedDateDisplay = '02 oct. 2026 · 14:08';

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>Intelligence ML</h1>
          <p className={styles.subtitle}>Modèle en production et performances</p>
        </div>
        <div className={styles.headerActions}>
          <Link to={PATHS.mlViz} className={styles.vizNavBtn}>
            Visualisations (PCA · t-SNE · UMAP) →
          </Link>
        </div>
      </header>

      <div className={styles.infoBanner} role="note">
        <strong>Valeurs illustratives de la maquette.</strong> La structure réelle est fournie par{' '}
        <code>GET /api/v1/ml/performance</code> (benchmark, tests statistiques, test final avec intervalles de
        confiance, équité) ; aucun résultat ML définitif n&apos;est affiché ici.
      </div>

      <div className={styles.tabsRow}>
        <div className={styles.tabGroup} role="tablist" aria-label="Sections de performance ML">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'overview'}
            className={`${styles.tabBtn} ${activeTab === 'overview' ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            Vue générale
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'comparison'}
            className={`${styles.tabBtn} ${activeTab === 'comparison' ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab('comparison')}
          >
            Comparaison
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'calibration'}
            className={`${styles.tabBtn} ${activeTab === 'calibration' ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab('calibration')}
          >
            Calibration
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'uncertainty'}
            className={`${styles.tabBtn} ${activeTab === 'uncertainty' ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab('uncertainty')}
          >
            Incertitude
          </button>
        </div>
      </div>

      {/* Top Row: Benchmark des 5 algorithmes + Modèle en production */}
      <section className={styles.topGrid}>
        <article className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Benchmark des 5 algorithmes</h2>
            <span className={styles.cardMeta}>jeu de validation</span>
          </div>

          <div className={styles.tableWrapper}>
            <table className={styles.benchmarkTable}>
              <thead>
                <tr>
                  <th>Algorithme</th>
                  <th>Accuracy</th>
                  <th>Précision</th>
                  <th>Rappel</th>
                  <th>F1</th>
                  <th>ROC-AUC</th>
                  <th>PR-AUC</th>
                  <th>MCC</th>
                  <th>Inf. (ms)</th>
                </tr>
              </thead>
              <tbody>
                {report.algorithms.map((alg) => (
                  <tr
                    key={alg.id}
                    className={alg.inProduction ? styles.productionRow : undefined}
                  >
                    <td className={styles.algNameCell}>
                      <span className={styles.algNameText}>{alg.name}</span>
                      {alg.inProduction && (
                        <span className={styles.prodBadge}>En production</span>
                      )}
                    </td>
                    <td className={styles.monoCell}>{formatDecimalFr(alg.accuracy, 3)}</td>
                    <td className={styles.monoCell}>{formatDecimalFr(alg.precision, 3)}</td>
                    <td className={styles.monoCell}>{formatDecimalFr(alg.recall, 3)}</td>
                    <td className={styles.monoCell}>{formatDecimalFr(alg.f1, 3)}</td>
                    <td className={styles.monoCell}>{formatDecimalFr(alg.rocAuc, 3)}</td>
                    <td className={styles.monoCell}>{formatDecimalFr(alg.prAuc, 3)}</td>
                    <td className={styles.monoCell}>{formatDecimalFr(alg.mcc, 3)}</td>
                    <td className={styles.monoCell}>{formatDecimalFr(alg.inferenceMs, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Modèle en production</h2>
            <span className={styles.demoPill}>
              {report.model.mode === 'real' ? 'Production' : 'Démonstration'}
            </span>
          </div>

          <dl className={styles.kvList}>
            <div className={styles.kvRow}>
              <dt>Nom</dt>
              <dd>{report.model.name}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>Version</dt>
              <dd>{report.model.version}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>Algorithme</dt>
              <dd>{report.model.algorithm}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>α</dt>
              <dd>{formatDecimalFr(report.model.alpha, 2)}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>Entraîné le</dt>
              <dd>{trainedDateDisplay}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>Commit Git</dt>
              <dd className={styles.monoValue}>{report.model.git_commit}</dd>
            </div>
          </dl>
        </article>
      </section>

      {/* Middle Row: Comparaison des modèles + Courbes ROC + Matrice de confusion */}
      <section className={styles.threeColGrid}>
        <article
          className={`${styles.card} ${activeTab === 'comparison' ? styles.cardHighlighted : ''}`}
        >
          <div className={styles.cardHeaderSplit}>
            <h2 className={styles.cardTitle}>Comparaison des modèles</h2>
            <div className={styles.chartLegendGrid}>
              <span className={styles.legendItem}>
                <i className={styles.dotPrecision} /> Précision
              </span>
              <span className={styles.legendItem}>
                <i className={styles.dotRecall} /> Rappel
              </span>
              <span className={styles.legendItem}>
                <i className={styles.dotF1} /> F1-score
              </span>
              <span className={styles.legendItem}>
                <i className={styles.dotRoc} /> ROC-AUC
              </span>
            </div>
          </div>

          <div className={styles.barChartContainer} aria-label="Graphique de comparaison des 5 modèles">
            {report.algorithms.map((alg) => {
              // Exact mockup formula: baseline 0.78 -> top 1.00
              const scaleBar = (v: number) => Math.max(15, Math.min(100, Math.round(((v - 0.78) / 0.22) * 100)));
              return (
                <div key={alg.id} className={styles.barGroup}>
                  <div className={styles.barsWrap}>
                    <div
                      className={`${styles.bar} ${styles.barPrecision}`}
                      style={{ height: `${scaleBar(alg.precision)}%` }}
                      title={`Précision : ${formatDecimalFr(alg.precision)}`}
                    />
                    <div
                      className={`${styles.bar} ${styles.barRecall}`}
                      style={{ height: `${scaleBar(alg.recall)}%` }}
                      title={`Rappel : ${formatDecimalFr(alg.recall)}`}
                    />
                    <div
                      className={`${styles.bar} ${styles.barF1}`}
                      style={{ height: `${scaleBar(alg.f1)}%` }}
                      title={`F1-score : ${formatDecimalFr(alg.f1)}`}
                    />
                    <div
                      className={`${styles.bar} ${styles.barRoc}`}
                      style={{ height: `${scaleBar(alg.rocAuc)}%` }}
                      title={`ROC-AUC : ${formatDecimalFr(alg.rocAuc)}`}
                    />
                  </div>
                  <span className={styles.barLabel}>{alg.shortLabel}</span>
                </div>
              );
            })}
          </div>
        </article>

        <article
          className={`${styles.card} ${activeTab === 'comparison' ? styles.cardHighlighted : ''}`}
        >
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Courbes ROC</h2>
          </div>

          <div className={styles.svgChartBox}>
            <svg
              viewBox="0 0 280 155"
              preserveAspectRatio="none"
              className={styles.rocSvg}
              role="img"
              aria-label="Courbes ROC des 5 modèles"
            >
              {/* Grid lines */}
              <line x1="20" y1="15" x2="265" y2="15" className={styles.gridLine} />
              <line x1="20" y1="55" x2="265" y2="55" className={styles.gridLine} />
              <line x1="20" y1="95" x2="265" y2="95" className={styles.gridLine} />
              <line x1="20" y1="135" x2="265" y2="135" className={styles.gridLine} />
              <line x1="20" y1="15" x2="20" y2="135" className={styles.gridLine} />
              <line x1="95" y1="15" x2="95" y2="135" className={styles.gridLine} />
              <line x1="175" y1="15" x2="175" y2="135" className={styles.gridLine} />
              <line x1="265" y1="15" x2="265" y2="135" className={styles.gridLine} />

              {/* Diagonal baseline */}
              <line x1="20" y1="135" x2="265" y2="15" className={styles.diagLine} />

              {/* Logistic Regression */}
              <path
                d="M 20 135 L 24 44 Q 42 26 95 21 L 265 15"
                fill="none"
                stroke="#9ca3af"
                strokeWidth="1.5"
              />
              {/* SVM */}
              <path
                d="M 20 135 L 23 36 Q 38 22 90 19 L 265 15"
                fill="none"
                stroke="#6fbf8b"
                strokeWidth="1.5"
              />
              {/* MLP */}
              <path
                d="M 20 135 L 22 31 Q 35 19 85 18 L 265 15"
                fill="none"
                stroke="#f5f5f5"
                strokeWidth="1.5"
              />
              {/* Random Forest */}
              <path
                d="M 20 135 L 21 26 Q 32 17 80 16.5 L 265 15"
                fill="none"
                stroke="#f59e0b"
                strokeWidth="1.6"
              />
              {/* Gradient Boosting (XGBoost) */}
              <path
                d="M 20 135 L 20.5 21 Q 28 15.5 72 15.2 L 265 15"
                fill="none"
                stroke="#ef4444"
                strokeWidth="2.2"
              />
            </svg>

            <div className={styles.axisMetaRow}>
              <span>Taux de faux positifs →</span>
              <span>↑ Rappel</span>
            </div>

            <div className={styles.rocLegend}>
              <span className={styles.legendItem}>
                <i className={styles.dotPrecision} /> Régression logistique
              </span>
              <span className={styles.legendItem}>
                <i className={styles.dotRecall} /> Random Forest
              </span>
              <span className={styles.legendItem}>
                <i className={styles.dotRoc} /> Gradient Boosting
              </span>
              <span className={styles.legendItem}>
                <i className={styles.dotF1} /> SVM
              </span>
              <span className={styles.legendItem}>
                <i className={styles.dotMlp} /> MLP
              </span>
            </div>
          </div>
        </article>

        <article className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Matrice de confusion</h2>
            <span className={styles.cardMeta}>XGBoost · test final</span>
          </div>

          <div className={styles.confusionGrid}>
            <div className={styles.confusionCellTn}>
              <span className={styles.confusionValue}>
                {formatNumberFr(report.confusionMatrix.tn)}
              </span>
              <span className={styles.confusionLabel}>Vrais négatifs</span>
            </div>
            <div className={styles.confusionCellFp}>
              <span className={styles.confusionValue}>
                {formatNumberFr(report.confusionMatrix.fp)}
              </span>
              <span className={styles.confusionLabel}>Faux positifs</span>
            </div>
            <div className={styles.confusionCellFn}>
              <span className={styles.confusionValue}>
                {formatNumberFr(report.confusionMatrix.fn)}
              </span>
              <span className={styles.confusionLabel}>Faux négatifs</span>
            </div>
            <div className={styles.confusionCellTp}>
              <span className={styles.confusionValue}>
                {formatNumberFr(report.confusionMatrix.tp)}
              </span>
              <span className={styles.confusionLabel}>Vrais positifs</span>
            </div>
          </div>
        </article>
      </section>

      {/* Bottom Row: Calibration + Incertitude et couverture + Validation statistique */}
      <section className={styles.threeColGrid}>
        <article
          className={`${styles.card} ${activeTab === 'calibration' ? styles.cardHighlighted : ''}`}
        >
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Calibration</h2>
            <span className={styles.cardMeta}>diagramme de fiabilité</span>
          </div>

          <div className={styles.svgChartBox}>
            <svg
              viewBox="0 0 280 150"
              preserveAspectRatio="none"
              className={styles.calibrationSvg}
              role="img"
              aria-label="Diagramme de fiabilité de calibration"
            >
              <line x1="20" y1="15" x2="265" y2="15" className={styles.gridLine} />
              <line x1="20" y1="55" x2="265" y2="55" className={styles.gridLine} />
              <line x1="20" y1="95" x2="265" y2="95" className={styles.gridLine} />
              <line x1="20" y1="135" x2="265" y2="135" className={styles.gridLine} />
              <line x1="80" y1="15" x2="80" y2="135" className={styles.gridLine} />
              <line x1="145" y1="15" x2="145" y2="135" className={styles.gridLine} />
              <line x1="210" y1="15" x2="210" y2="135" className={styles.gridLine} />

              {/* Ideal diagonal */}
              <line x1="20" y1="135" x2="265" y2="15" className={styles.diagLine} />

              {/* Calibrated reliability curve */}
              <path
                d="M 20 133 C 75 115, 130 78, 195 42 C 228 24, 248 18, 265 15"
                fill="none"
                stroke="#ef4444"
                strokeWidth="2.2"
              />
            </svg>

            <div className={styles.axisMetaRow}>
              <span>Probabilité prédite</span>
              <span>ECE {formatDecimalFr(report.eceScore, 3)} · illustratif</span>
            </div>
          </div>
        </article>

        <article
          className={`${styles.card} ${activeTab === 'uncertainty' ? styles.cardHighlighted : ''}`}
        >
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Incertitude et couverture</h2>
          </div>

          <dl className={styles.kvList}>
            <div className={styles.kvRow}>
              <dt>Couverture visée (1 − α)</dt>
              <dd>{formatPctFr(report.conformal.targetCoveragePct)}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>Couverture mesurée</dt>
              <dd>{formatPctFr(report.conformal.measuredCoveragePct)}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>Part d&apos;ensembles {'{0,1}'} ou vides</dt>
              <dd>{formatPctFr(report.conformal.reviewSetRatePct)}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>Part d&apos;incertitude ÉLEVÉE</dt>
              <dd>{formatPctFr(report.conformal.highUncertaintyRatePct)}</dd>
            </div>
          </dl>

          <p className={styles.cardFootNote}>
            Mesures en production via les labels simulés (chargebacks).
          </p>
        </article>

        <article className={styles.card}>
          <div className={styles.cardHeader}>
            <h2 className={styles.cardTitle}>Validation statistique</h2>
          </div>

          <dl className={styles.kvList}>
            <div className={styles.kvRow}>
              <dt>Test de Friedman</dt>
              <dd>{report.statistical.friedmanPValue}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>Wilcoxon + Holm</dt>
              <dd>{report.statistical.wilcoxonHolm}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>IC 95 % du F1 (test final)</dt>
              <dd className={styles.monoValue}>{report.statistical.f1ConfidenceInterval95}</dd>
            </div>
            <div className={styles.kvRow}>
              <dt>Équité (genre)</dt>
              <dd>{report.statistical.genderFairnessGap}</dd>
            </div>
          </dl>
        </article>
      </section>
    </div>
  );
}
