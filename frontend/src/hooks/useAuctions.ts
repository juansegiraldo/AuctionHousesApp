import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Auction, PaginatedResponse, AuctionSearchFilters } from '@/types/api';

export function useAuctions(
  filters?: AuctionSearchFilters & { limit?: number; offset?: number },
  options?: Omit<UseQueryOptions<PaginatedResponse<Auction>>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['auctions', filters],
    queryFn: () => api.auctions.getAll(filters).then(res => res.data),
    ...options,
  });
}

export function useAuction(
  id: number,
  options?: Omit<UseQueryOptions<Auction>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['auction', id],
    queryFn: () => api.auctions.getById(id).then(res => res.data),
    enabled: !!id,
    ...options,
  });
}

export function useAuctionBySlug(
  slug: string,
  options?: Omit<UseQueryOptions<Auction>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['auction', 'slug', slug],
    queryFn: () => api.auctions.getBySlug(slug).then(res => res.data),
    enabled: !!slug,
    ...options,
  });
}

export function useUpcomingAuctions(
  params?: { limit?: number; offset?: number },
  options?: Omit<UseQueryOptions<PaginatedResponse<Auction>>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['auctions', 'upcoming', params],
    queryFn: () => api.auctions.getUpcoming(params).then(res => res.data),
    ...options,
  });
}

export function useLiveAuctions(
  params?: { limit?: number; offset?: number },
  options?: Omit<UseQueryOptions<PaginatedResponse<Auction>>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['auctions', 'live', params],
    queryFn: () => api.auctions.getLive(params).then(res => res.data),
    refetchInterval: 30000, // Refetch every 30 seconds for live auctions
    ...options,
  });
}

export function useRecentAuctions(
  params?: { limit?: number; offset?: number },
  options?: Omit<UseQueryOptions<PaginatedResponse<Auction>>, 'queryKey' | 'queryFn'>
) {
  return useQuery({
    queryKey: ['auctions', 'recent', params],
    queryFn: () => api.auctions.getRecent(params).then(res => res.data),
    ...options,
  });
}