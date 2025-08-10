export interface AuctionHouse {
  id: number;
  name: string;
  country: string;
  city?: string;
  website?: string;
  description?: string;
  specialties: string[];
  established_year?: number;
  logo_url?: string;
  verified: boolean;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Artist {
  id: number;
  name: string;
  birth_year?: number;
  death_year?: number;
  nationality?: string;
  biography?: string;
  art_movement?: string;
  verified: boolean;
  wikidata_id?: string;
  created_at: string;
  updated_at: string;
}

export interface Category {
  id: number;
  name: string;
  description?: string;
  parent_id?: number;
  level: number;
  path: string;
  created_at: string;
  updated_at: string;
}

export interface Auction {
  id: number;
  house_id: number;
  title: string;
  description?: string;
  start_date: string;
  end_date?: string;
  exhibition_start?: string;
  exhibition_end?: string;
  status: 'draft' | 'upcoming' | 'live' | 'preview' | 'completed' | 'cancelled';
  location?: string;
  auction_type: 'live' | 'online' | 'hybrid';
  slug: string;
  external_id?: string;
  external_url?: string;
  currency: string;
  total_lots: number;
  total_estimate_min?: number;
  total_estimate_max?: number;
  total_realized?: number;
  sale_rate?: number;
  created_at: string;
  updated_at: string;
  
  // Relations
  house?: AuctionHouse;
  lots?: Lot[];
}

export interface Lot {
  id: number;
  auction_id: number;
  artist_id?: number;
  category_id?: number;
  lot_number: string;
  title: string;
  description?: string;
  medium?: string;
  dimensions?: string;
  condition?: string;
  provenance?: string;
  estimated_price_min?: number;
  estimated_price_max?: number;
  final_price?: number;
  sold: boolean;
  currency: string;
  images?: string[];
  external_id?: string;
  external_url?: string;
  created_at: string;
  updated_at: string;
  
  // Relations
  auction?: Auction;
  artist?: Artist;
  category?: Category;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export interface AuctionSearchFilters {
  house_id?: number;
  status?: string[];
  auction_type?: string[];
  country?: string;
  currency?: string;
  start_date_from?: string;
  start_date_to?: string;
  search?: string;
}

export interface LotSearchFilters {
  auction_id?: number;
  artist_id?: number;
  category_id?: number;
  min_price?: number;
  max_price?: number;
  currency?: string;
  sold?: boolean;
  search?: string;
}

export interface ApiError {
  detail: string;
  code?: string;
}