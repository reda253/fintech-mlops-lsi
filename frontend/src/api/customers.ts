import { apiRequest } from './client';
import type {
  Customer,
  CustomerDetailResponse,
  CustomerListFilters,
  CustomerListResponse,
} from '@/types/customer';

export const customersApi = {
  list: (filters: CustomerListFilters = {}) =>
    apiRequest<CustomerListResponse>('/customers', {
      method: 'GET',
      query: {
        name: filters.q || undefined,
        city: filters.city || undefined,
        state: filters.state || undefined,
        cardLast4: filters.cardLast4 || undefined,
        page: Math.max(0, (filters.page ?? 1) - 1),
        size: filters.pageSize ?? 10,
        sort: `${filters.sortBy ?? 'createdAt'},${filters.sortDir ?? 'desc'}`,
      },
    }),

  get: (id: string) => apiRequest<CustomerDetailResponse>(`/customers/${id}`),

  create: (payload: CreateCustomerPayload) =>
    apiRequest<Customer>('/customers', { method: 'POST', body: payload }),

  update: (id: string, payload: UpdateCustomerPayload) =>
    apiRequest<Customer>(`/customers/${id}`, { method: 'PUT', body: payload }),
};

export interface CreateCustomerPayload {
  firstName: string;
  lastName: string;
  gender: 'F' | 'M';
  birthDate: string;
  profession: string;
  street: string;
  city: string;
  state: string;
  zipCode: string;
  cityPopulation: number;
  latitude: number;
  longitude: number;
  cardNumber: string;
}

export type UpdateCustomerPayload = Omit<CreateCustomerPayload, 'cardNumber'>;