'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, FileText, BarChart3, Terminal, X } from 'lucide-react';

interface SidebarProps {
  mobileOpen?: boolean;
  onClose?: () => void;
}

const navItems = [
  { label: 'Home', href: '/', icon: LayoutDashboard },
  { label: 'Disputes', href: '/disputes', icon: FileText },
  { label: 'Cost Dashboard', href: '/dashboard', icon: BarChart3 },
  { label: 'API Logs', href: '/logs', icon: Terminal },
];

export default function Sidebar({ mobileOpen = false, onClose }: SidebarProps) {
  const pathname = usePathname();

  const sidebarContent = (
    <div className="flex flex-col h-full" style={{ background: '#0D1117', borderRight: '1px solid #1F2937' }}>
      {/* Logo */}
      <div className="flex items-center justify-between px-5 py-5 border-b" style={{ borderColor: '#1F2937' }}>
        <div className="flex items-center gap-3">
          <span className="text-2xl">⚖️</span>
          <div>
            <span className="font-bold text-white text-lg leading-none block">NyayaNode</span>
            <span
              className="text-xs font-semibold px-1.5 py-0.5 rounded mt-0.5 inline-block"
              style={{ background: 'rgba(245,158,11,0.15)', color: '#F59E0B', border: '1px solid rgba(245,158,11,0.3)' }}
            >
              ONDC · DPI
            </span>
          </div>
        </div>
        {/* Mobile close button */}
        {onClose && (
          <button
            onClick={onClose}
            className="lg:hidden p-1 rounded"
            style={{ color: '#9CA3AF' }}
            aria-label="Close sidebar"
          >
            <X size={20} />
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ label, href, icon: Icon }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              onClick={onClose}
              className={`
                flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium
                transition-all duration-150 w-full
                ${isActive
                  ? 'nav-active'
                  : 'text-[#9CA3AF] hover:bg-[#1F2937] hover:text-[#F9FAFB]'
                }
              `}
              style={isActive ? { borderLeft: '3px solid #F59E0B', color: '#F59E0B', background: 'rgba(245,158,11,0.08)', paddingLeft: '9px' } : {}}
            >
              <Icon size={18} className="flex-shrink-0" />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t" style={{ borderColor: '#1F2937' }}>
        <p className="text-xs" style={{ color: '#4B5563' }}>
          🇮🇳 National Digital Infrastructure
        </p>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col w-60 flex-shrink-0 h-screen sticky top-0">
        {sidebarContent}
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60"
            onClick={onClose}
          />
          {/* Drawer */}
          <aside className="relative w-60 flex-shrink-0 h-full z-10">
            {sidebarContent}
          </aside>
        </div>
      )}
    </>
  );
}
