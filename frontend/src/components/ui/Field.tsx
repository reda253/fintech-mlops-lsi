import { useId, useState, type InputHTMLAttributes } from 'react';
import { cx } from '@/lib/cx';
import { Icon } from './Icon';
import styles from './Field.module.css';

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  invalid?: boolean;
  /** Affiche le bouton œil (champ mot de passe). */
  revealable?: boolean;
}

export function Field({ label, invalid, revealable, type = 'text', className, ...rest }: FieldProps) {
  const id = useId();
  const [revealed, setRevealed] = useState(false);
  const effectiveType = revealable && revealed ? 'text' : type;

  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <div className={styles.control}>
        <input
          id={id}
          type={effectiveType}
          aria-invalid={invalid || undefined}
          className={cx(styles.input, invalid && styles.invalid, revealable && styles.withAction, className)}
          {...rest}
        />
        {revealable && (
          <button
            type="button"
            className={styles.reveal}
            onClick={() => setRevealed((v) => !v)}
            aria-label={revealed ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
            aria-pressed={revealed}
          >
            <Icon name={revealed ? 'eyeOff' : 'eye'} size={18} />
          </button>
        )}
      </div>
    </div>
  );
}
