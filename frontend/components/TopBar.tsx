'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Menu } from 'lucide-react';

const pageTitles: Record<string, string> = {
  '/': 'Dashboard Overview',
  '/disputes': 'Disputes',
  '/dashboard': 'Cost Dashboard',
  '/logs': 'API Logs',
  '/agent': 'Live Agent Negotiation',
};

interface TopBarProps {
  onMenuClick?: () => void;
}

export default function TopBar({ onMenuClick }: TopBarProps) {
  const pathname = usePathname();
  const [time, setTime] = useState('');

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      const istOptions: Intl.DateTimeFormatOptions = {
        timeZone: 'Asia/Kolkata',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      };
      const formatted = now.toLocaleTimeString('en-IN', istOptions);
      setTime(`${formatted} IST`);
    };

    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  const pageTitle = pageTitles[pathname] ?? 'NyayaNode';

  return (
    <header
      className="flex items-center justify-between px-6 flex-shrink-0"
      style={{
        height: '56px',
        background: '#0D1117',
        borderBottom: '1px solid #1F2937',
      }}
    >
      {/* Left: hamburger (mobile) + page title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-1.5 rounded hover:bg-[#1F2937] transition-colors"
          style={{ color: '#9CA3AF' }}
          aria-label="Open menu"
        >
          <Menu size={20} />
        </button>
        <h1 className="font-semibold text-base" style={{ color: '#F9FAFB' }}>
          {pageTitle}
        </h1>
      </div>

      {/* Right: clock + live badge */}
      <div className="flex items-center gap-4">
        <span
          className="text-sm font-mono tabular-nums"
          style={{ color: '#9CA3AF' }}
        >
          {time}
        </span>
        <div
          className="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold"
          style={{
            background: 'rgba(16, 185, 129, 0.1)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            color: '#10B981',
          }}
        >
          <span
            className="pulse-dot w-2 h-2 rounded-full flex-shrink-0"
            style={{ background: '#10B981' }}
          />
          System Live
        </div>
      </div>
    </header>
  );
}
