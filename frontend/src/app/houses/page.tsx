'use client';

import { useHouses } from '@/hooks/useHouses';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Globe, MapPin } from '@/components/ui/icons';
import Link from 'next/link';

export default function HousesPage() {
  const { data: housesResponse, isLoading, error } = useHouses();
  
  const houses = housesResponse?.items || [];

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-lg">Cargando casas de subastas...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-lg text-red-600">
            Error al cargar las casas de subastas: {error.message}
          </div>
        </div>
      </div>
    );
  }

  if (!houses || houses.length === 0) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="text-lg text-gray-600">
            No se encontraron casas de subastas.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Casas de Subastas
        </h1>
        <p className="text-gray-600">
          Explora las principales casas de subastas y sus colecciones de arte.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {houses.map((house) => (
          <Card key={house.id} className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="flex items-start justify-between">
                <CardTitle className="text-xl font-semibold line-clamp-2">
                  {house.name}
                </CardTitle>
                <Badge variant="secondary" className="ml-2">
                  {house.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center text-gray-600">
                  <MapPin className="h-4 w-4 mr-2" />
                  <span>{house.country}</span>
                </div>

                {house.website && (
                  <div className="flex items-center text-gray-600">
                    <Globe className="h-4 w-4 mr-2" />
                    <a 
                      href={house.website} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:text-blue-800 underline"
                    >
                      Sitio web
                    </a>
                  </div>
                )}

                {house.description && (
                  <p className="text-gray-700 line-clamp-3">
                    {house.description}
                  </p>
                )}

                <div className="pt-2">
                  <Link 
                    href={`/houses/${house.id}`}
                    className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                  >
                    Ver Subastas
                  </Link>
                </div>

                {house.last_scrape && (
                  <div className="text-xs text-gray-500">
                    Última actualización: {new Date(house.last_scrape).toLocaleDateString('es-ES')}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}