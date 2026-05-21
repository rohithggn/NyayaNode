'use client';

import { useEffect, useState } from 'react';
import LogTable, { MOCK_LOGS } from '@/components/LogTable';

export default function LogsPage() {
  const [isLive, setIsLive]     = useState(false);
  const [logCount, setLogCount] = useState(12);

  useEffect(() => {
    if (!isLive) return;
    const interval = setInterval(() => {
      setLogCount(c => Math.min(c + 1, 24));
    }, 2200);
    return () => clearInterval(interval);
  }, [isLive]);

  // Cycle mock logs beyond 12 by repeating the array
  const displayLogs = Array.from({ length: logCount }, (_, i) => ({
    ...MOCK_LOGS[i % MOCK_LOGS.length],
    id: `log-${i}`,
    timestamp: `14:3${Math.floor(i / 10)}:${String(i % 60).padStart(2, '0')} IST`,
  }));

  return (
    <div className="min-h-screen p-6" style={{ background: '#0A0F1E' }}>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">API &amp; Inference Logs</h2>
          <p className="text-sm mt-1" style={{ color: '#9CA3AF' }}>
            Real-time ONDC network calls · Hindsight memory operations · Cascadeflow routing decisions
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsLive(v => !v)}
            className="px-5 py-2.5 rounded-xl text-sm font-bold transition-all hover:scale-[1.02] hover:brightness-110"
            style={isLive
              ? { background: '#1F2937', color: '#9CA3AF', border: '1px solid #374151' }
              : { background: '#F59E0B', color: '#0A0F1E' }}
          >
            {isLive ? '■ Pause' : '● Go Live'}
          </button>
          {isLive && (
            <span className="text-amber-400 text-xs font-bold px-3 py-1 rounded-full animate-pulse"
              style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.35)' }}>
              LIVE
            </span>
          )}
        </div>
      </div>

      {/* Summary bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Total API Calls',      value: logCount,                        color: '#F59E0B' },
          { label: 'Hindsight Ops',        value: Math.floor(logCount * 0.3),      color: '#3B82F6' },
          { label: 'Cascadeflow Routes',   value: Math.floor(logCount * 0.4),      color: '#10B981' },
          { label: 'Error Rate',           value: '8.3%',                          color: '#DC2626' },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-xl p-4" style={{ background: '#111827', border: '1px solid #1F2937' }}>
            <p className="text-xs uppercase tracking-wider mb-2" style={{ color: '#4B5563' }}>{label}</p>
            <p className="text-2xl font-bold" style={{ color }}>{value}</p>
          </div>
        ))}
      </div>

      {/* Log table */}
      <LogTable logs={displayLogs} isLive={isLive} />
    </div>
  );
}
