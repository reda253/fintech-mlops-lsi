/**
 * Types du domaine "Customer" — conformes au contrat des maquettes 04/05/06.
 * Le backend (service customers via la gateway) renvoie exactement ces champs.
 */

export type CustomerGender = 'F' | 'M';

export type TransactionStatus = 'APPROUVEE' | 'BLOQUEE' | 'EN_REVUE';

export interface Customer {
  id: string;
  firstName: string;
  lastName: string;
  gender: CustomerGender;
  /** Date ISO (YYYY-MM-DD) */
  birthDate: string;
  profession: string;
  street: string;
  city: string;
  /** Code d'État sur 2 lettres majuscules (ex. NC) */
  state: string;
  zipCode: string;
  cityPopulation: number;
  latitude: number;
  longitude: number;
  /** 4 derniers chiffres uniquement — jamais le PAN complet */
  cardLast4: string;
  createdAt: string;
  updatedAt: string;
}

export interface CustomerListFilters {
  /** Nom ou prénom */
  q?: string;
  city?: string;
  state?: string;
  /** 4 derniers chiffres de la carte */
  cardLast4?: string;
  page?: number;
  pageSize?: number;
  sortBy?: 'createdAt' | 'lastName' | 'city';
  sortDir?: 'asc' | 'desc';
}

export interface CustomerListResponse {
  items: Customer[];
  total: number;
  page: number;
  pageSize: number;
}

export interface CustomerTransaction {
  id: string;
  /** Identifiant tronqué affiché dans la maquette (ex. 613b9873…) */
  reference: string;
  occurredAt: string;
  amount: number;
  currency: string;
  category: string;
  status: TransactionStatus;
  /** Probabilité de fraude entre 0 et 1 */
  fraudProbability: number;
}

export interface CustomerDetailResponse {
  customer: Customer;
  stats: {
    total: number;
    approved: number;
    blocked: number;
    inReview: number;
  };
  transactions: CustomerTransaction[];
}
