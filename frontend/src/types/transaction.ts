import type { TransactionStatus } from './customer';

export type DecisionSource = 'AUTO' | 'MANUELLE';
export type RiskDecision = 'APPROUVER' | 'REVUE' | 'BLOQUER';
export type DecisionReason =
  | 'MODELE_CONFIANT'
  | 'MODELE_INCERTAIN'
  | 'ML_INDISPONIBLE'
  | 'CLIENT_INDISPONIBLE';
export type UncertaintyLevel = 'FAIBLE' | 'ELEVEE';

export type FullTransactionStatus = TransactionStatus | 'EN_ATTENTE';

export interface TransactionRiskSummary {
  decision: RiskDecision;
  reason: DecisionReason;
  fraudProbability: number | null;
  predictionSet: number[] | null;
  uncertainty: number | null;
  uncertaintyLevel?: UncertaintyLevel | null;
  modelVersion: string | null;
  reviewId?: string | null;
}

export interface TransactionItem {
  id: string;
  transNum: string;
  customerId: string;
  customerFirstName: string;
  customerLastName: string;
  cardLast4: string;
  transDateTime: string;
  amount: number;
  currency: string;
  category: string;
  merchant: string;
  merchLat: number;
  merchLong: number;
  status: FullTransactionStatus;
  decisionSource: DecisionSource | null;
  risk: TransactionRiskSummary | null;
  createdAt: string;
  updatedAt: string;
}

export interface TransactionListFilters {
  customerId?: string;
  status?: FullTransactionStatus;
  minAmount?: number;
  maxAmount?: number;
  from?: string;
  to?: string;
  page?: number;
  pageSize?: number;
  sort?: string;
}

export interface TransactionListResponse {
  items: TransactionItem[];
  total: number;
  page: number;
  pageSize: number;
}