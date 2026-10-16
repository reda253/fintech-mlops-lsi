import type { HTMLAttributes } from 'react';
import { cx } from '@/lib/cx';
import styles from './Card.module.css';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Texture de points en haut à droite (cartes KPI). */
  dotted?: boolean;
  padded?: boolean;
}

export function Card({ dotted, padded = true, className, ...rest }: CardProps) {
  return <div className={cx(styles.card, dotted && styles.dotted, padded && styles.padded, className)} {...rest} />;
}
