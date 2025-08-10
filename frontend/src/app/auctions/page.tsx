'use client';

import { useAuctions } from '@/hooks/useAuctions';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Calendar, MapPin } from '@/components/ui/icons';
import Link from 'next/link';

export default function AuctionsPage() {
  const { data: auctionsResponse, isLoading, error } = useAuctions();
  
  const auctions = auctionsResponse?.items || [];

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-lg">Cargando subastas...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-lg text-red-600">
            Error al cargar las subastas: {error.message}
          </div>
        </div>
      </div>
    );
  }

  if (!auctions || auctions.length === 0) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-lg text-gray-600">
            No se encontraron subastas.
          </div>
        </div>
      </div>
    );
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'upcoming': return 'primary';
      case 'active': return 'success';
      case 'completed': return 'secondary';
      default: return 'secondary';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'upcoming': return 'Próxima';
      case 'active': return 'En vivo';
      case 'completed': return 'Finalizada';
      default: return status;
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Subastas
        </h1>
        <p className="text-gray-600">
          Explora las subastas de arte en curso y próximas.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {auctions.map((auction) => (
          <Card key={auction.id} className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="flex items-start justify-between">
                <CardTitle className="text-xl font-semibold line-clamp-2">
                  {auction.title}
                </CardTitle>
                <Badge variant={getStatusColor(auction.status)} className="ml-2">
                  {getStatusText(auction.status)}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {auction.house_name && (
                  <div className="text-gray-600 font-medium">
                    {auction.house_name}
                  </div>
                )}

                {auction.start_date && (
                  <div className="flex items-center text-gray-600">
                    <Calendar className="h-4 w-4 mr-2" />
                    <span>
                      {new Date(auction.start_date).toLocaleDateString('es-ES', {
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric'
                      })}
                    </span>
                  </div>
                )}

                {auction.location && (
                  <div className="flex items-center text-gray-600">
                    <MapPin className="h-4 w-4 mr-2" />
                    <span>{auction.location}</span>
                  </div>
                )}

                {auction.description && (
                  <p className="text-gray-700 line-clamp-3">
                    {auction.description}
                  </p>
                )}

                <div className="flex items-center justify-between">
                  {auction.total_lots > 0 && (
                    <div className="text-sm text-gray-600">
                      {auction.total_lots} lotes
                    </div>
                  )}
                  
                  {auction.total_realized && (
                    <div className="text-sm font-medium text-green-600">
                      €{auction.total_realized.toLocaleString()}
                    </div>
                  )}
                </div>

                <div className="pt-2">
                  <Link 
                    href={`/auctions/${auction.id}`}
                    className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                  >
                    Ver Lotes
                  </Link>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}