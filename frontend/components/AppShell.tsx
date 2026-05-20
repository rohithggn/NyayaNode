'use client';

import { useState } from 'react';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import MobileNav from './MobileNav';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#0A0F1E' }}>
      {/* Mobile top nav (visible on small screens only) */}
      <MobileNav />

      {/* Sidebar (hidden on mobile, shown on lg+) */}
      <div className="hidden lg:flex flex-col flex-shrink-0">
        <Sidebar
          mobileOpen={mobileOpen}
          onClose={() => setMobileOpen(false)}
        />
      </div>

      {/* Main column */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden pt-14 lg:pt-0">
        <TopBar onMenuClick={() => setMobileOpen(true)} />
        <main
          className="flex-1 overflow-y-auto p-6"
          style={{ background: '#0A0F1E' }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
