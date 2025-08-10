import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Lot, PaginatedResponse, LotSearchFilters } from '@/types/api';

export function useLots(
  filters?: LotSearchFilters & { limit?: number; offset?: number },
  options?: Omit<UseQueryOptions<PaginatedResponse<Lot>>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['lots', filters],
    queryFn: () => api.lots.getAll(filters).then(res => res.data),
    ...options,
  });
}

export function useLot(
  id: number,
  options?: Omit<UseQueryOptions<Lot>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['lot', id],
    queryFn: () => api.lots.getById(id).then(res => res.data),
    enabled: !!id,
    ...options,
  });
}

export function useSearchLots(
  query: string,
  params?: { limit?: number; offset?: number },
  options?: Omit<UseQueryOptions<PaginatedResponse<Lot>>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['lots', 'search', query, params],
    queryFn: () => api.lots.search({ q: query, ...params }).then(res => res.data),
    enabled: !!query && query.length > 2,
    ...options,
  });
}

export function useRecentLots(
  params?: { limit?: number; offset?: number },
  options?: Omit<UseQueryOptions<PaginatedResponse<Lot>>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['lots', 'recent', params],
    queryFn: () => api.lots.getRecent(params).then(res => res.data),
    ...options,
  });
}

export function useLotsByAuction(
  auctionId: number,
  params?: { limit?: number; offset?: number },
  options?: Omit<UseQueryOptions<PaginatedResponse<Lot>>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['lots', 'auction', auctionId, params],
    queryFn: () => api.lots.getByAuction(auctionId, params).then(res => res.data),
    enabled: !!auctionId,
    ...options,
  });
}