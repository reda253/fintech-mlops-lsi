/** Statuts métier d'une transaction (contrat transaction-service). */
export type TransactionStatus = 'EN_ATTENTE' | 'EN_REVUE' | 'APPROUVEE' | 'BLOQUEE';

/** États d'une revue humaine (contrat risk-service). */
export type ReviewStatus = 'OUVERTE' | 'TRAITEE';

/** Types de notification (contrat notification-service). */
export type NotificationType = 'BLOCAGE' | 'REVUE';
