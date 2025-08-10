'use client';

import Link from 'next/link';
import { useHouses } from '@/hooks/useHouses';
import { useAuctions } from '@/hooks/useAuctions';
import { useLots } from '@/hooks/useLots';
import { Calendar, Globe, Tag } from '@/components/ui/icons';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function HomeContent() {
  const { data: houses, isLoading: housesLoading } = useHouses({ limit: 6 });
  const { data: auctions, isLoading: auctionsLoading } = useAuctions({ limit: 4 });
  const { data: lots, isLoading: lotsLoading } = useLots({ limit: 8 });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Hero Section */}
      <div className="text-center py-12">
        <h1 className="text-4xl font-bold text-gray-900 sm:text-5xl md:text-6xl">
          Base de Datos Mundial de Subastas de Arte
        </h1>
        <p className="mt-3 max-w-md mx-auto text-base text-gray-500 sm:text-lg md:mt-5 md:text-xl md:max-w-3xl">
          Rastrea subastas, descubre obras de arte y analiza tendencias del mercado de las principales casas de subastas del mundo.
        </p>
        <div className="mt-5 max-w-md mx-auto sm:flex sm:justify-center md:mt-8">
          <div className="rounded-md shadow">
            <Link
              href="/houses"
              className="w-full flex items-center justify-center px-8 py-3 border border-transparent text-base font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 md:py-4 md:text-lg md:px-10"
            >
              Comenzar Exploración
            </Link>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 mb-8">
        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Globe className="h-6 w-6 text-gray-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Casas de Subastas</dt>
                  <dd className="text-lg font-medium text-gray-900">
                    {houses ? houses.total.toLocaleString() : '—'}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Calendar className="h-6 w-6 text-gray-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Subastas Activas</dt>
                  <dd className="text-lg font-medium text-gray-900">
                    {auctions ? auctions.total.toLocaleString() : '—'}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white overflow-hidden shadow rounded-lg">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Tag className="h-6 w-6 text-gray-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="text-sm font-medium text-gray-500 truncate">Obras de Arte</dt>
                  <dd className="text-lg font-medium text-gray-900">
                    {lots ? lots.total.toLocaleString() : '—'}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Featured Auction Houses */}
        <Card>
          <CardHeader>
            <CardTitle>Casas de Subastas Destacadas</CardTitle>
          </CardHeader>
          <CardContent>
            {housesLoading ? (
              <div className="animate-pulse space-y-4">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="h-16 bg-gray-200 rounded"></div>
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                {houses?.items.slice(0, 4).map((house) => (
                  <div key={house.id} className="flex items-center space-x-4">
                    <div className="flex-shrink-0">
                      <div className="h-10 w-10 bg-blue-100 rounded-full flex items-center justify-center">
                        <Globe className="h-6 w-6 text-blue-600" />
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <Link href={`/houses/${house.id}`} className="text-sm font-medium text-gray-900 hover:text-blue-600">
                        {house.name}
                      </Link>
                      <p className="text-sm text-gray-500">{house.country}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4">
              <Link href="/houses" className="text-sm font-medium text-blue-600 hover:text-blue-500">
                Ver todas las casas →
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Recent Auctions */}
        <Card>
          <CardHeader>
            <CardTitle>Subastas Recientes</CardTitle>
          </CardHeader>
          <CardContent>
            {auctionsLoading ? (
              <div className="animate-pulse space-y-4">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="h-16 bg-gray-200 rounded"></div>
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                {auctions?.items.slice(0, 4).map((auction) => (
                  <div key={auction.id} className="border-l-4 border-blue-500 pl-4">
                    <Link href={`/auctions/${auction.id}`} className="text-sm font-medium text-gray-900 hover:text-blue-600">
                      {auction.title}
                    </Link>
                    <p className="text-sm text-gray-500 flex items-center mt-1">
                      <Calendar className="h-4 w-4 mr-1" />
                      {auction.start_date && new Date(auction.start_date).toLocaleDateString('es-ES')}
                    </p>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4">
              <Link href="/auctions" className="text-sm font-medium text-blue-600 hover:text-blue-500">
                Ver todas las subastas →
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Artworks */}
      <div className="mt-8">
        <Card>
          <CardHeader>
            <CardTitle>Obras de Arte Agregadas Recientemente</CardTitle>
          </CardHeader>
          <CardContent>
            {lotsLoading ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="animate-pulse">
                    <div className="h-48 bg-gray-200 rounded-lg"></div>
                    <div className="mt-2 h-4 bg-gray-200 rounded"></div>
                    <div className="mt-1 h-3 bg-gray-200 rounded w-3/4"></div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {lots?.items.slice(0, 4).map((lot) => (
                  <div key={lot.id} className="group">
                    <div className="aspect-square bg-gray-100 rounded-lg overflow-hidden group-hover:opacity-75 transition-opacity">
                      <div className="w-full h-full flex items-center justify-center">
                        <Tag className="h-12 w-12 text-gray-400" />
                      </div>
                    </div>
                    <div className="mt-2">
                      <Link href={`/lots/${lot.id}`} className="text-sm font-medium text-gray-900 hover:text-blue-600">
                        {lot.title}
                      </Link>
                      <p className="text-sm text-gray-500">{lot.artist_name}</p>
                      {lot.estimated_price_min && lot.estimated_price_max && (
                        <p className="text-sm text-gray-900 font-medium">
                          €{lot.estimated_price_min.toLocaleString()} - €{lot.estimated_price_max.toLocaleString()}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-6">
              <Link href="/lots" className="text-sm font-medium text-blue-600 hover:text-blue-500">
                Ver todas las obras →
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}