import type { ReactNode } from 'react';
import { cx } from '@/lib/cx';
import styles from './Alert.module.css';

interface AlertProps {
  tone?: 'danger' | 'warning' | 'success' | 'info';
  children: ReactNode;
  className?: string;
}

/** Message en ligne. `role="alert"` pour que les lecteurs d'écran annoncent l'erreur. */
export function Alert({ tone = 'danger', children, className }: AlertProps) {
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={cx(styles.alert, styles[tone], className)}>
      {children}
    </div>
  );
}
