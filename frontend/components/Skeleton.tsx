'use client';

// ─── SkeletonCard ─────────────────────────────────────────────────────────────
export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div
      className="rounded-xl p-6 animate-pulse"
      style={{ background: '#111827', border: '1px solid #1F2937' }}
    >
      <div className="h-3 rounded mb-4" style={{ background: '#1F2937', width: '33%' }} />
      <div className="flex flex-col gap-2">
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className="h-2.5 rounded"
            style={{ background: '#1F2937', width: i % 2 === 0 ? '100%' : '66%' }}
          />
        ))}
      </div>
    </div>
  );
}

// ─── SkeletonTable ────────────────────────────────────────────────────────────
const COL_WIDTHS = ['w-20', 'w-32', 'w-24', 'w-16', 'w-20'];
const ROW_WIDTHS = [
  ['w-20', 'w-36', 'w-24', 'w-16', 'w-20'],
  ['w-16', 'w-28', 'w-20', 'w-12', 'w-24'],
  ['w-24', 'w-32', 'w-16', 'w-20', 'w-16'],
  ['w-20', 'w-24', 'w-28', 'w-16', 'w-20'],
  ['w-16', 'w-36', 'w-20', 'w-24', 'w-16'],
];

export function SkeletonTable() {
  return (
    <div
      className="rounded-xl overflow-hidden animate-pulse"
      style={{ background: '#111827', border: '1px solid #1F2937' }}
    >
      {/* Header */}
      <div className="h-10 flex gap-4 px-6 items-center" style={{ background: '#0D1117' }}>
        {COL_WIDTHS.map((w, i) => (
          <div key={i} className={`${w} h-2.5 rounded`} style={{ background: '#1F2937' }} />
        ))}
      </div>
      {/* Rows */}
      {ROW_WIDTHS.map((cols, r) => (
        <div
          key={r}
          className="h-14 flex gap-4 px-6 items-center"
          style={{ borderTop: '1px solid #1F2937' }}
        >
          {cols.map((w, c) => (
            <div key={c} className={`${w} h-2.5 rounded`} style={{ background: '#1F2937' }} />
          ))}
        </div>
      ))}
    </div>
  );
}

// ─── SkeletonGauge ────────────────────────────────────────────────────────────
export function SkeletonGauge() {
  return (
    <div
      className="rounded-xl p-6 animate-pulse flex flex-col items-center gap-4"
      style={{ background: '#111827', border: '1px solid #1F2937' }}
    >
      <div className="w-40 h-20 rounded-t-full" style={{ background: '#1F2937' }} />
      <div className="w-24 h-3 rounded"   style={{ background: '#1F2937' }} />
      <div className="w-36 h-2.5 rounded" style={{ background: '#1F2937' }} />
    </div>
  );
}
