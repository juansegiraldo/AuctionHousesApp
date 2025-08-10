import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { AuctionHouse, PaginatedResponse } from '@/types/api';

export function useHouses(
  params?: { limit?: number; offset?: number; country?: string; verified?: boolean },
  options?: Omit<UseQueryOptions<PaginatedResponse<AuctionHouse>>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['houses', params],
    queryFn: () => api.houses.getAll(params).then(res => res.data),
    ...options,
  });
}

export function useHouse(
  id: number,
  options?: Omit<UseQueryOptions<AuctionHouse>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['house', id],
    queryFn: () => api.houses.getById(id).then(res => res.data),
    enabled: !!id,
    ...options,
  });
}

export function useHouseStats(
  id: number,
  options?: Omit<UseQueryOptions<any>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['house', id, 'stats'],
    queryFn: () => api.houses.getStats(id).then(res => res.data),
    enabled: !!id,
    ...options,
  });
}