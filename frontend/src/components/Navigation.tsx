'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, Building2, Hammer, Palette, Search, BarChart3 } from 'lucide-react';

const navigationItems = [
  { href: '/', label: 'Home', icon: Home },
  { href: '/houses', label: 'Auction Houses', icon: Building2 },
  { href: '/auctions', label: 'Auctions', icon: Hammer },
  { href: '/lots', label: 'Artworks', icon: Palette },
  { href: '/search', label: 'Search', icon: Search },
  { href: '/analytics', label: 'Analytics', icon: BarChart3 },
];

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav className="border-b border-gray-200 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex">
            <Link href="/" className="flex items-center px-4 text-lg font-bold text-gray-900">
              🏛️ Auction Houses DB
            </Link>
            <div className="hidden md:ml-6 md:flex md:space-x-8">
              {navigationItems.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  className={`inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium ${
                    pathname === href
                      ? 'border-blue-500 text-gray-900'
                      : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
                  }`}
                >
                  <Icon className="w-4 h-4 mr-2" />
                  {label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
      
      {/* Mobile menu */}
      <div className="md:hidden">
        <div className="pt-2 pb-3 space-y-1">
          {navigationItems.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`block pl-3 pr-4 py-2 border-l-4 text-base font-medium ${
                pathname === href
                  ? 'bg-blue-50 border-blue-500 text-blue-700'
                  : 'border-transparent text-gray-500 hover:bg-gray-50 hover:border-gray-300 hover:text-gray-700'
              }`}
            >
              <div className="flex items-center">
                <Icon className="w-4 h-4 mr-2" />
                {label}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}