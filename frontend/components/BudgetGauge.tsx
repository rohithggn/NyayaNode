'use client';

interface BudgetGaugeProps {
  currentCost: number;
  budgetLimit?: number;
  cascadeEnabled: boolean;
}

export default function BudgetGauge({ currentCost, budgetLimit = 5, cascadeEnabled }: BudgetGaugeProps) {
  const percent     = Math.min((currentCost / budgetLimit) * 100, 100);
  const isNearLimit = percent > 75;
  const isOver      = currentCost > budgetLimit;

  const ARC_LEN     = 251.2; // π × 80
  const dashOffset  = ARC_LEN - (percent / 100) * ARC_LEN;
  const arcColor    = isOver ? '#DC2626' : isNearLimit ? '#F59E0B' : '#10B981';
  const textColor   = arcColor;

  // Status pill
  let pillBg: string, pillText: string, pillLabel: string;
  if (cascadeEnabled && !isOver) {
    pillBg = 'rgba(16,185,129,0.15)'; pillText = '#10B981';
    pillLabel = '✓ Cascadeflow keeping cost in budget';
  } else if (cascadeEnabled && isOver) {
    pillBg = 'rgba(220,38,38,0.15)'; pillText = '#DC2626';
    pillLabel = '⚠ Budget exceeded even with Cascadeflow';
  } else if (!cascadeEnabled && isOver) {
    pillBg = 'rgba(220,38,38,0.15)'; pillText = '#DC2626';
    pillLabel = '🔥 Over budget — Cascadeflow is OFF';
  } else {
    pillBg = 'rgba(75,85,99,0.3)'; pillText = '#9CA3AF';
    pillLabel = 'Cascadeflow OFF — cost unoptimized';
  }

  const arcProps = {
    cx: 100, cy: 100, r: 80,
    fill: 'none', strokeWidth: 16, strokeLinecap: 'round' as const,
    strokeDasharray: ARC_LEN,
    transform: 'rotate(180, 100, 100)',
  };

  return (
    <div
      className="flex flex-col items-center rounded-xl p-6"
      style={{ background: '#111827', border: '1px solid #1F2937' }}
    >
      <p className="text-xs font-medium uppercase tracking-widest mb-4" style={{ color: '#4B5563' }}>
        Budget Gauge
      </p>

      <svg viewBox="0 0 200 120" width="100%" style={{ maxWidth: 220 }}>
        {/* Background arc */}
        <circle {...arcProps} stroke="#1F2937" strokeDashoffset={0} />

        {/* Foreground arc */}
        <circle
          {...arcProps}
          stroke={arcColor}
          strokeDashoffset={dashOffset}
          style={{ transition: 'stroke-dashoffset 0.6s ease, stroke 0.4s ease' }}
        />

        {/* Center text */}
        <text x={100} textAnchor="middle" y={85} fontSize={22} fontWeight={700} fill={textColor}>
          ₹{currentCost.toFixed(2)}
        </text>
        <text x={100} textAnchor="middle" y={103} fontSize={10} fill="#6B7280">
          of ₹{budgetLimit} limit
        </text>
      </svg>

      {/* Status pill */}
      <span
        className="text-xs px-3 py-1 rounded-full font-medium mt-2 text-center"
        style={{ background: pillBg, color: pillText, border: `1px solid ${pillText}40` }}
      >
        {pillLabel}
      </span>
    </div>
  );
}
