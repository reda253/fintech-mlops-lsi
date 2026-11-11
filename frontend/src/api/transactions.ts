import { apiRequest } from './client';
import type {
  TransactionItem,
  TransactionListFilters,
  TransactionListResponse,
} from '@/types/transaction';

interface BackendTransactionPageDto {
  content?: TransactionItem[];
  items?: TransactionItem[];
  page?: {
    number: number;
    size: number;
    totalElements: number;
    totalPages: number;
  };
  total?: number;
}

export const transactionsApi = {
  list: async (filters: TransactionListFilters = {}): Promise<TransactionListResponse> => {
    const page1 = filters.page ?? 1;
    const size = filters.pageSize ?? 10;

    const raw = await apiRequest<BackendTransactionPageDto>('/transactions', {
      method: 'GET',
      query: {
        customerId: filters.customerId || undefined,
        status: filters.status || undefined,
        minAmount: filters.minAmount !== undefined ? filters.minAmount : undefined,
        maxAmount: filters.maxAmount !== undefined ? filters.maxAmount : undefined,
        from: filters.from || undefined,
        to: filters.to || undefined,
        page: Math.max(0, page1 - 1),
        size,
        sort: filters.sort ?? 'transDateTime,desc',
      },
    });

    const rows = raw.content ?? raw.items ?? [];
    const total = raw.page?.totalElements ?? raw.total ?? rows.length;

    return {
      items: rows,
      total,
      page: page1,
      pageSize: size,
    };
  },

  get: (id: string) => apiRequest<TransactionItem>(`/transactions/${id}`),
};