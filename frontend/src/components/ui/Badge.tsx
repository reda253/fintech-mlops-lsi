import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';
import styles from './Badge.module.css';

export type BadgeTone = 'neutral' | 'danger' | 'warning' | 'success' | 'accent';

interface BadgeProps {
  tone?: BadgeTone;
  /** Variante pilule à bordure pointillée (ex. « Données simulées »). */
  dashed?: boolean;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = 'neutral', dashed, children, className }: BadgeProps) {
  return <span className={cx(styles.badge, styles[tone], dashed && styles.dashed, className)}>{children}</span>;
}

/** Compteur de navigation (ex. « 38 », « 5 »). */
export function CountPill({ value, label }: { value: number; label?: string }) {
  return (
    <span className={styles.count} aria-label={label}>
      {value}
    </span>
  );
}
