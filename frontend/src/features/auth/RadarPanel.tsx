import styles from './RadarPanel.module.css';

const RINGS = [69, 150, 223, 322, 400];
const TICKS = Array.from({ length: 60 }, (_, i) => i * 6);

/** Dots « transactions » : décalage (x, y) par rapport au centre, en px CSS. */
const DOTS = [
  { x: 52, y: -125, size: 7 },
  { x: -124, y: 54, size: 7 },
  { x: 100, y: 100, size: 7 },
];

/** Panneau gauche de la page de connexion : radar de risque + cartes flottantes (maquette 01). */
export function RadarPanel() {
  return (
    <section className={styles.panel} aria-label="Présentation de la plateforme">
      <div className={styles.radar} aria-hidden="true">
        <div className={styles.sweep} />
        <svg viewBox="-400 -400 800 800" className={styles.rings}>
          <g fill="none" stroke="rgba(255,255,255,0.075)" strokeWidth="1">
            {RINGS.map((r) => (
              <circle key={r} r={r} />
            ))}
            <path d="M-400 0H400M0 -400V400M-283 -283L283 283M283 -283L-283 283" stroke="rgba(255,255,255,0.05)" />
          </g>
          <g stroke="rgba(255,255,255,0.22)" strokeWidth="1">
            {TICKS.map((deg) => {
              const long = deg % 30 === 0;
              const a = (deg * Math.PI) / 180;
              const r1 = 400;
              const r2 = long ? 384 : 391;
              return (
                <line
                  key={deg}
                  x1={Math.sin(a) * r1}
                  y1={-Math.cos(a) * r1}
                  x2={Math.sin(a) * r2}
                  y2={-Math.cos(a) * r2}
                />
              );
            })}
          </g>
        </svg>
        {DOTS.map((d) => (
          <span
            key={`${d.x}:${d.y}`}
            className={styles.dot}
            style={{ left: `calc(50% + ${d.x}px)`, top: `calc(50% + ${d.y}px)`, width: d.size, height: d.size }}
          />
        ))}
        <span className={styles.core} />
      </div>

      <article className={`${styles.float} ${styles.cardA}`}>
        <p className={styles.fLabel}>Transaction évaluée</p>
        <p className={styles.fValue}>
          0,96 <span className={styles.chip}>BLOQUER</span>
        </p>
        <p className={styles.fMeta}>Ensemble [1] · incertitude 0,05</p>
      </article>

      <article className={`${styles.float} ${styles.cardB}`}>
        <p className={styles.fLabel}>Modèle en production</p>
        <p className={styles.fStrong}>fraud-detector v8</p>
        <p className={styles.fMeta}>Prédiction conforme · α = 0,05</p>
      </article>

      <article className={`${styles.float} ${styles.cardC}`}>
        <p className={styles.fLabel}>File de revue humaine</p>
        <p className={styles.fValue}>38 revues</p>
        <p className={styles.fMeta}>statut OUVERTE</p>
      </article>

      <div className={styles.pitch}>
        <h2 className={styles.headline}>Chaque transaction, évaluée avant qu’elle ne devienne un risque.</h2>
        <p className={styles.tags}>Scoring ML · Incertitude · Revue humaine · Traçabilité</p>
      </div>
    </section>
  );
}
