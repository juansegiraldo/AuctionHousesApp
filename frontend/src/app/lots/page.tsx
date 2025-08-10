'use client';

import { useLots } from '@/hooks/useLots';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tag } from '@/components/ui/icons';
import Link from 'next/link';

export default function LotsPage() {
  const { data: lotsResponse, isLoading, error } = useLots();
  
  const lots = lotsResponse?.items || [];

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-lg">Cargando lotes...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-lg text-red-600">
            Error al cargar los lotes: {error.message}
          </div>
        </div>
      </div>
    );
  }

  if (!lots || lots.length === 0) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-lg text-gray-600">
            No se encontraron lotes.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Lotes de Arte
        </h1>
        <p className="text-gray-600">
          Explora las obras de arte disponibles en las subastas.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {lots.map((lot) => (
          <Card key={lot.id} className="hover:shadow-lg transition-shadow">
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-gray-500 mb-1">
                    Lote {lot.lot_number}
                  </div>
                  <CardTitle className="text-lg font-semibold line-clamp-2">
                    {lot.title}
                  </CardTitle>
                </div>
                <Badge variant={lot.sold ? 'success' : 'secondary'} className="ml-2">
                  {lot.sold ? 'Vendido' : 'Disponible'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {lot.artist_name && (
                  <div className="text-gray-700 font-medium">
                    {lot.artist_name}
                  </div>
                )}

                {lot.medium && (
                  <div className="flex items-center text-gray-600 text-sm">
                    <Tag className="h-3 w-3 mr-1" />
                    <span>{lot.medium}</span>
                  </div>
                )}

                {lot.dimensions && (
                  <div className="text-gray-600 text-sm">
                    {lot.dimensions}
                  </div>
                )}

                <div className="space-y-1">
                  {lot.estimated_price_min && lot.estimated_price_max && (
                    <div className="text-sm text-gray-600">
                      Estimación: €{lot.estimated_price_min.toLocaleString()} - €{lot.estimated_price_max.toLocaleString()}
                    </div>
                  )}
                  
                  {lot.final_price && (
                    <div className="text-sm font-medium text-green-600">
                      Precio final: €{lot.final_price.toLocaleString()}
                    </div>
                  )}
                </div>

                {lot.description && (
                  <p className="text-gray-700 text-sm line-clamp-2">
                    {lot.description}
                  </p>
                )}

                <div className="pt-2">
                  <Link 
                    href={`/lots/${lot.id}`}
                    className="inline-flex items-center px-3 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                  >
                    Ver Detalles
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