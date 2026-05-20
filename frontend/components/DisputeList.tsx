'use client';

import { useState } from 'react';
import { ArrowRight, Clock } from 'lucide-react';
import type { Dispute, DisputeStatus } from '@/lib/mockData';

interface DisputeListProps {
  disputes: Dispute[];
  selectedId: string | null;
  onSelect: (dispute: Dispute) => void;
}

const statusStyles: Record<DisputeStatus, { bg: string; color: string; border: string }> = {
  Resolved:      { bg: 'rgba(16,185,129,0.1)',  color: '#10B981', border: 'rgba(16,185,129,0.3)' },
  'In Progress': { bg: 'rgba(245,158,11,0.1)',  color: '#F59E0B', border: 'rgba(245,158,11,0.3)' },
  Escalated:     { bg: 'rgba(220,38,38,0.1)',   color: '#DC2626', border: 'rgba(220,38,38,0.3)' },
};

const filterOptions: Array<'All' | DisputeStatus> = ['All', 'Resolved', 'In Progress', 'Escalated'];

export default function DisputeList({ disputes, selectedId, onSelect }: DisputeListProps) {
  const [search, setSearch]   = useState('');
  const [filter, setFilter]   = useState<'All' | DisputeStatus>('All');

  const filtered = disputes.filter(d => {
    const matchFilter = filter === 'All' || d.status === filter;
    const q = search.toLowerCase();
    const matchSearch = !q || d.id.toLowerCase().includes(q) || d.buyerApp.toLowerCase().includes(q);
    return matchFilter && matchSearch;
  });

  return (
    <div className="flex flex-col gap-3">
      {/* Controls */}
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Search by Case ID or Buyer App…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="flex-1 rounded-lg px-4 py-2.5 text-sm outline-none"
          style={{ background: '#0D1117', border: '1px solid #374151', color: '#F9FAFB' }}
        />
        <select
          value={filter}
          onChange={e => setFilter(e.target.value as typeof filter)}
          className="rounded-lg px-3 py-2.5 text-sm outline-none"
          style={{ background: '#0D1117', border: '1px solid #374151', color: '#9CA3AF' }}
        >
          {filterOptions.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      </div>

      {/* List */}
      <div className="flex flex-col gap-2 overflow-y-auto" style={{ maxHeight: '400px' }}>
        {filtered.length === 0 && (
          <p className="text-sm text-center py-8" style={{ color: '#4B5563' }}>No disputes found.</p>
        )}
        {filtered.map(d => {
          const isSelected = d.id === selectedId;
          const s = statusStyles[d.status as DisputeStatus] ?? statusStyles['In Progress'];
          return (
            <div
              key={d.id}
              onClick={() => onSelect(d)}
              className="rounded-xl p-4 cursor-pointer transition-all duration-150 group"
              style={{
                background: isSelected ? '#1a2035' : '#111827',
                border: isSelected ? '1px solid #F59E0B' : '1px solid #1F2937',
                borderLeft: isSelected ? '4px solid #F59E0B' : '1px solid #1F2937',
              }}
            >
              {/* Top row */}
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs font-semibold" style={{ color: '#F59E0B' }}>
                  {d.id}
                </span>
                <span
                  className="text-xs font-semibold px-2 py-0.5 rounded-full"
                  style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}
                >
                  {d.status}
                </span>
              </div>

              {/* Middle row */}
              <div className="flex items-center gap-2 mb-2">
                <span className="text-sm font-medium" style={{ color: '#F9FAFB' }}>{d.buyerApp}</span>
                <ArrowRight size={13} style={{ color: '#4B5563' }} />
                <span className="text-sm" style={{ color: '#9CA3AF' }}>{d.sellerApp}</span>
              </div>

              {/* Bottom row */}
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold" style={{ color: '#F9FAFB' }}>
                  {d.amount.toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })}
                </span>
                <div className="flex items-center gap-2">
                  <span
                    className="text-xs px-2 py-0.5 rounded-full"
                    style={{ background: 'rgba(245,158,11,0.08)', color: '#9CA3AF', border: '1px solid #1F2937' }}
                  >
                    {d.category}
                  </span>
                  {d.resolutionTime !== '—' && (
                    <span className="flex items-center gap-1 text-xs" style={{ color: '#10B981' }}>
                      <Clock size={11} />
                      {d.resolutionTime}
                    </span>
                  )}
                </div>
              </div>

              {/* View Timeline hint */}
              <div
                className="mt-2 text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity"
                style={{ color: '#F59E0B' }}
              >
                View Timeline →
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
