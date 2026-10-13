import { useId } from 'react';
import styles from './Logo.module.css';

interface LogoMarkProps {
  height?: number;
  className?: string;
}

/**
 * Logo : bouclier à dégradé orange → rouge, jauge de risque à trois arcs,
 * aiguille blanche (maquette 00_COMMUN_logo.png). Reconstruit en SVG vectoriel.
 */
export function LogoMark({ height = 32, className }: LogoMarkProps) {
  const gid = useId();
  return (
    <svg
      className={className}
      height={height}
      viewBox="0 0 64 76"
      fill="none"
      role="img"
      aria-label="FinTech Risk Intelligence"
    >
      <defs>
        <linearGradient id={gid} x1="6" y1="3" x2="58" y2="73" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FF7A45" />
          <stop offset="1" stopColor="#D93A2B" />
        </linearGradient>
      </defs>
      <path
        d="M32 4 57 14.500V38c0 15.500-11.500 27-25 33.500C18.500 65 7 53.500 7 38V14.500Z"
        stroke={`url(#${gid})`}
        strokeWidth="4.600"
        strokeLinejoin="round"
        fill="rgba(0,0,0,0.35)"
      />
      <g strokeLinecap="round" strokeWidth="3.600" stroke="#F04B23">
        <path d="M9 47a19 19 0 0 1 38 0" opacity=".28" transform="translate(0 0)" />
        <path d="M15 47a13 13 0 0 1 26 0" opacity=".55" />
        <path d="M21.500 47a6.500 6.500 0 0 1 13 0" opacity=".9" />
      </g>
      <path d="M28 47 42.500 30" stroke="#F04B23" strokeWidth="4" strokeLinecap="round" />
      <circle cx="28" cy="47" r="4" fill="#F04B23" />
      <circle cx="43.500" cy="29" r="3.800" fill="#F5F5F5" />
    </svg>
  );
}

interface LogoProps {
  /** Variante réduite : uniquement l'icône (sidebar repliée). */
  compact?: boolean;
  /** Variante large (carte de connexion) : icône 48 px, texte 18 px. */
  large?: boolean;
}

export function Logo({ compact = false, large = false }: LogoProps) {
  return (
    <span className={`${styles.logo} ${large ? styles.large : ''}`}>
      <LogoMark height={large ? 48 : 30} />
      {!compact && (
        <span className={styles.text}>
          <span className={styles.name}>FinTech Risk</span>
          <span className={styles.sub}>Intelligence</span>
        </span>
      )}
    </span>
  );
}
