'use client';

import { useEffect, useRef, useState } from 'react';
import BudgetGauge from '@/components/BudgetGauge';
import CascadeToggle from '@/components/CascadeToggle';
import ModelRouterChart from '@/components/ModelRouterChart';

interface CostEvent { model: string; costInr: number; taskType: string; timestamp: string; }

const TASKS = ['Read tracking status','Format buyer complaint','Parse logistics API','Extract order details',
  'Draft settlement proposal','Validate policy clause','Summarize evidence','Counter-proposal analysis',
  'Format final terms','Issue binding verdict'];

const costEvents_ON: CostEvent[] = [
  { model:'phi-3-mini',    costInr:0.001 }, { model:'phi-3-mini',    costInr:0.001 },
  { model:'gpt-3.5-turbo', costInr:0.003 }, { model:'phi-3-mini',    costInr:0.001 },
  { model:'claude-haiku',  costInr:0.004 }, { model:'phi-3-mini',    costInr:0.001 },
  { model:'phi-3-mini',    costInr:0.001 }, { model:'claude-haiku',  costInr:0.004 },
  { model:'phi-3-mini',    costInr:0.001 }, { model:'claude-sonnet', costInr:0.018 },
].map((e, i) => ({ ...e, taskType: TASKS[i], timestamp: `14:33:0${i} IST` })) as CostEvent[];

const costEvents_OFF: CostEvent[] = TASKS.map((taskType, i) => ({
  model: 'gpt-4o', costInr: 0.062, taskType, timestamp: `14:33:0${i} IST`,
}));

const MODEL_COLORS: Record<string, string> = {
  'phi-3-mini':'#3B82F6','gpt-3.5-turbo':'#F59E0B','claude-haiku':'#10B981',
  'claude-sonnet':'#8B5CF6','gpt-4o':'#DC2626',
};

export default function DashboardPage() {
  const [cascadeEnabled, setCascadeEnabled] = useState(true);
  const [isSimulating, setIsSimulating]     = useState(false);
  const [visibleEvents, setVisibleEvents]   = useState<CostEvent[]>([]);
  const [currentIndex, setCurrentIndex]     = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const activeScript = cascadeEnabled ? costEvents_ON : costEvents_OFF;
  const totalCost    = visibleEvents.reduce((s, e) => s + e.costInr, 0);
  const gpt4oEquiv   = visibleEvents.length * 0.062;
  const savings      = Math.max(0, gpt4oEquiv - totalCost);
  const savingsPct   = Math.round((1 - totalCost / Math.max(gpt4oEquiv, 0.001)) * 100);

  useEffect(() => {
    if (!isSimulating) return;
    if (currentIndex >= activeScript.length) { setIsSimulating(false); return; }
    timerRef.current = setTimeout(() => {
      setVisibleEvents(prev => [...prev, activeScript[currentIndex]]);
      setCurrentIndex(i => i + 1);
    }, 600);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [isSimulating, currentIndex, activeScript]);

  function handleToggle() {
    setCascadeEnabled(v => !v);
    setVisibleEvents([]); setCurrentIndex(0); setIsSimulating(false);
  }
  function handleSimulate() {
    setVisibleEvents([]); setCurrentIndex(0); setIsSimulating(true);
  }

  return (
    <div className="min-h-screen p-6" style={{ background: '#0A0F1E' }}>
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">Cost Intelligence Dashboard</h2>
          <p className="text-sm mt-0.5" style={{ color: '#9CA3AF' }}>
            Cascadeflow real-time model routing · ₹5 per-dispute budget enforcement
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleSimulate}
            disabled={isSimulating}
            className="px-5 py-2.5 rounded-xl text-sm font-bold transition-all hover:scale-[1.02] hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ background: '#F59E0B', color: '#0A0F1E' }}
          >
            ▶ Simulate Dispute
          </button>
          {isSimulating && (
            <span className="text-amber-400 text-sm font-medium animate-pulse flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />Routing...
            </span>
          )}
        </div>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="flex flex-col gap-4">
          <CascadeToggle enabled={cascadeEnabled} onToggle={handleToggle} />
          <BudgetGauge currentCost={totalCost * 10} budgetLimit={5} cascadeEnabled={cascadeEnabled} />
        </div>
        <div className="lg:col-span-2">
          <ModelRouterChart events={visibleEvents} />
        </div>
      </div>

      {/* Live event feed */}
      <div className="mt-6 rounded-xl p-6" style={{ background: '#111827', border: '1px solid #1F2937' }}>
        <p className="text-sm uppercase tracking-widest mb-4" style={{ color: '#9CA3AF' }}>Live Routing Log</p>
        <div className="flex flex-col-reverse gap-2 overflow-y-auto" style={{ maxHeight: 192 }}>
          {visibleEvents.map((e, i) => (
            <div key={i} className="flex justify-between items-center rounded-lg px-4 py-2" style={{ background: '#0D1117' }}>
              <span className="text-sm text-white">{e.taskType}</span>
              <span className="font-mono text-xs" style={{ color: MODEL_COLORS[e.model] ?? '#9CA3AF' }}>{e.model}</span>
              <div className="flex items-center gap-3 ml-4">
                <span className="text-sm font-semibold text-white">₹{e.costInr.toFixed(3)}</span>
                <span className="text-xs" style={{ color: '#6B7280' }}>{e.timestamp}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Comparison bar */}
      <div className="mt-6 grid grid-cols-3 gap-4">
        {[
          { label: 'This Session Cost',  value: `₹${totalCost.toFixed(4)}`,  color: '#F59E0B', sub: null },
          { label: 'GPT-4o Equivalent',  value: `₹${gpt4oEquiv.toFixed(3)}`, color: '#DC2626', sub: null },
          { label: 'Savings',            value: `₹${savings.toFixed(3)}`,    color: '#10B981', sub: `${savingsPct}% reduction` },
        ].map(({ label, value, color, sub }) => (
          <div key={label} className="rounded-xl p-4 text-center" style={{ background: '#111827', border: '1px solid #1F2937' }}>
            <p className="text-xs uppercase tracking-wider mb-2" style={{ color: '#4B5563' }}>{label}</p>
            <p className="text-2xl font-bold" style={{ color }}>{value}</p>
            {sub && <p className="text-xs mt-1" style={{ color: '#6B7280' }}>{sub}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}
