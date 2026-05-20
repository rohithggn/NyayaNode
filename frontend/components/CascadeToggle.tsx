'use client';

import { motion } from 'framer-motion';

interface CascadeToggleProps {
  enabled: boolean;
  onToggle: () => void;
}

const STATS = (enabled: boolean) => [
  { label: 'Routing Strategy', value: enabled ? 'Smart SLM-first' : 'Flagship only',  color: enabled ? '#10B981' : '#DC2626' },
  { label: 'Est. Savings',     value: enabled ? '40–85%'          : '0%',              color: enabled ? '#10B981' : '#6B7280' },
  { label: 'Budget Guard',     value: enabled ? 'Active'          : 'Disabled',        color: enabled ? '#F59E0B' : '#6B7280' },
  { label: 'Latency Added',    value: enabled ? '<1ms'            : '—',               color: '#3B82F6'                       },
];

export default function CascadeToggle({ enabled, onToggle }: CascadeToggleProps) {
  return (
    <div className="rounded-xl p-6" style={{ background: '#111827', border: '1px solid #1F2937' }}>
      {/* Top row */}
      <div className="flex justify-between items-center">
        <div>
          <p className="text-white font-semibold text-base">Cascadeflow Engine</p>
          <p className="text-xs mt-0.5" style={{ color: '#9CA3AF' }}>
            Intelligent model routing · Budget enforcement
          </p>
        </div>

        {/* Toggle switch */}
        <div
          onClick={onToggle}
          className="relative flex items-center cursor-pointer rounded-full transition-colors duration-300 flex-shrink-0"
          style={{ width: 56, height: 28, background: enabled ? '#F59E0B' : '#374151' }}
        >
          <motion.div
            className="absolute rounded-full bg-white shadow-md"
            style={{ width: 20, height: 20, top: 4 }}
            animate={{ x: enabled ? 28 : 4 }}
            transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          />
        </div>
      </div>

      {/* Stat cards */}
      <div className="mt-4 grid grid-cols-2 gap-3">
        {STATS(enabled).map(({ label, value, color }) => (
          <div key={label} className="rounded-lg p-3" style={{ background: '#0D1117' }}>
            <p className="text-xs mb-1" style={{ color: '#6B7280' }}>{label}</p>
            <p className="text-sm font-semibold" style={{ color }}>{value}</p>
          </div>
        ))}
      </div>

      {/* Bottom routing info */}
      <div className="mt-4 pt-4" style={{ borderTop: '1px solid #1F2937' }}>
        {enabled ? (
          <p className="text-xs" style={{ color: '#10B981' }}>
            ● Simple tasks → phi-3-mini (₹0.001) · Complex tasks → claude-haiku (₹0.004) · Legal decisions → claude-sonnet (₹0.018)
          </p>
        ) : (
          <p className="text-xs" style={{ color: '#DC2626' }}>
            ⚠ All tasks routing to gpt-4o at ₹0.06+ per call — budget drain active
          </p>
        )}
      </div>
    </div>
  );
}
