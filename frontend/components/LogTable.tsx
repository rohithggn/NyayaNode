'use client';

import { useState } from 'react';

interface ApiLog {
  id: string; timestamp: string; endpoint: string;
  method: 'GET' | 'POST' | 'PATCH'; model: string;
  latencyMs: number; costInr: number; status: 200 | 422 | 500;
  disputeId: string; payload: string;
}

const MODEL_COST: Record<string, number> = {
  'phi-3-mini': 0.001, 'gpt-3.5-turbo': 0.003, 'claude-haiku': 0.004,
  'claude-sonnet': 0.018, 'gpt-4o': 0.062,
};
const MODEL_COLOR: Record<string, string> = {
  'phi-3-mini': '#3B82F6', 'gpt-3.5-turbo': '#F59E0B', 'claude-haiku': '#10B981',
  'claude-sonnet': '#8B5CF6', 'gpt-4o': '#DC2626',
};
const METHOD_COLOR: Record<string, string> = { GET: '#3B82F6', POST: '#F59E0B', PATCH: '#10B981' };
const STATUS_COLOR: Record<number, string> = { 200: '#10B981', 422: '#F59E0B', 500: '#DC2626' };
const LATENCIES = [88, 142, 210, 95, 178, 305, 130, 260, 82, 340, 115, 198];
const HINDSIGHT = ['observation', 'world-fact', 'rollback', 'observation', 'world-fact',
  'world-fact', 'observation', 'world-fact', 'observation', 'rollback', 'observation', 'rollback'];

const RAW: Pick<ApiLog, 'endpoint' | 'method' | 'model' | 'status'>[] = [
  { endpoint: '/ondc/dispute/file',        method: 'POST',  model: 'phi-3-mini',    status: 200 },
  { endpoint: '/hindsight/memory/store',   method: 'POST',  model: 'gpt-3.5-turbo', status: 200 },
  { endpoint: '/logistics/tracking',       method: 'GET',   model: 'phi-3-mini',    status: 200 },
  { endpoint: '/hindsight/memory/rollback',method: 'POST',  model: 'claude-haiku',  status: 200 },
  { endpoint: '/cascadeflow/route',        method: 'POST',  model: 'claude-haiku',  status: 200 },
  { endpoint: '/ondc/settlement/propose',  method: 'POST',  model: 'claude-sonnet', status: 200 },
  { endpoint: '/ondc/settlement/accept',   method: 'PATCH', model: 'phi-3-mini',    status: 200 },
  { endpoint: '/hindsight/memory/fetch',   method: 'GET',   model: 'gpt-3.5-turbo', status: 200 },
  { endpoint: '/cascadeflow/budget/check', method: 'GET',   model: 'phi-3-mini',    status: 200 },
  { endpoint: '/ondc/verdict/issue',       method: 'POST',  model: 'claude-sonnet', status: 200 },
  { endpoint: '/logistics/tracking',       method: 'GET',   model: 'phi-3-mini',    status: 422 },
  { endpoint: '/ondc/dispute/file',        method: 'POST',  model: 'gpt-4o',        status: 500 },
];

export const MOCK_LOGS: ApiLog[] = RAW.map((r, i) => ({
  ...r, id: `log-${i}`,
  timestamp: `14:33:0${i} IST`,
  latencyMs: LATENCIES[i],
  costInr: MODEL_COST[r.model],
  disputeId: `NYA-284${i}`,
  payload: `{"disputeId":"NYA-284${i}","action":"${r.endpoint.split('/').pop()}"}`,
}));

type MethodFilter = 'ALL' | 'GET' | 'POST' | 'PATCH';
type StatusFilter = 'ALL' | 200 | 422 | 500;

export default function LogTable({ logs, isLive }: { logs: ApiLog[]; isLive: boolean }) {
  const [search, setSearch]         = useState('');
  const [methodF, setMethodF]       = useState<MethodFilter>('ALL');
  const [statusF, setStatusF]       = useState<StatusFilter>('ALL');
  const [expanded, setExpanded]     = useState<string | null>(null);

  const filtered = logs.filter(l => {
    const q = search.toLowerCase();
    return (!q || l.endpoint.includes(q) || l.disputeId.toLowerCase().includes(q))
      && (methodF === 'ALL' || l.method === methodF)
      && (statusF === 'ALL' || l.status === statusF);
  });

  const pill = (label: string, active: boolean, color: string, onClick: () => void) => (
    <button key={label} onClick={onClick}
      className="px-3 py-1 rounded-full text-xs font-medium transition-all"
      style={{ border: `1px solid ${active ? color : '#374151'}`, color: active ? color : '#6B7280', background: active ? `${color}18` : 'transparent' }}>
      {label}
    </button>
  );

  return (
    <div className="rounded-xl overflow-hidden" style={{ background: '#111827', border: '1px solid #1F2937' }}>
      <div className="flex flex-wrap gap-3 p-4" style={{ borderBottom: '1px solid #1F2937' }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search endpoint or dispute ID…"
          className="rounded-lg px-3 py-2 text-sm outline-none flex-1 min-w-[180px]"
          style={{ background: '#0D1117', border: '1px solid #374151', color: '#F9FAFB' }} />
        <div className="flex gap-1.5">
          {(['ALL','GET','POST','PATCH'] as MethodFilter[]).map(m => pill(m, methodF===m, '#F59E0B', () => setMethodF(m)))}
        </div>
        <div className="flex gap-1.5">
          {(['ALL',200,422,500] as StatusFilter[]).map(s => pill(String(s), statusF===s, s===200?'#10B981':s===422?'#F59E0B':'#DC2626', () => setStatusF(s as StatusFilter)))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead style={{ background: '#0D1117' }}>
            <tr>{['Time','Method','Endpoint','Model','Latency','Cost','Status','Dispute ID'].map(h => (
              <th key={h} className="px-4 py-3 text-xs uppercase tracking-widest" style={{ color: '#6B7280' }}>{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {filtered.map((log, idx) => {
              const isNewest = isLive && idx === 0;
              const isOpen   = expanded === log.id;
              return [
                <tr key={log.id} onClick={() => setExpanded(isOpen ? null : log.id)}
                  className={`cursor-pointer transition-colors border-b ${isNewest ? 'animate-pulse' : ''}`}
                  style={{ borderColor: '#1F2937', background: isOpen ? '#1a2035' : undefined }}>
                  <td className="px-4 py-3 text-xs font-mono" style={{ color: '#6B7280' }}>{log.timestamp}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-xs font-mono" style={{ background: `${METHOD_COLOR[log.method]}18`, color: METHOD_COLOR[log.method] }}>{log.method}</span>
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-white">{log.endpoint}</td>
                  <td className="px-4 py-3 text-xs font-mono" style={{ color: MODEL_COLOR[log.model] ?? '#9CA3AF' }}>{log.model}</td>
                  <td className="px-4 py-3 text-sm" style={{ color: log.latencyMs > 250 ? '#F59E0B' : '#D1D5DB' }}>{log.latencyMs}ms</td>
                  <td className="px-4 py-3 text-sm" style={{ color: '#D1D5DB' }}>₹{log.costInr.toFixed(4)}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-xs font-bold" style={{ background: `${STATUS_COLOR[log.status]}18`, color: STATUS_COLOR[log.status] }}>{log.status}</span>
                  </td>
                  <td className="px-4 py-3 text-xs font-mono" style={{ color: '#F59E0B' }}>{log.disputeId}</td>
                </tr>,
                isOpen && (
                  <tr key={`${log.id}-exp`} style={{ background: '#0D1117' }}>
                    <td colSpan={8} className="px-6 py-3">
                      <div className="flex justify-between text-xs font-mono" style={{ color: '#9CA3AF' }}>
                        <span>Payload: {log.payload}</span>
                        <span>Hindsight Tag: <span style={{ color: '#F59E0B' }}>{HINDSIGHT[parseInt(log.id.split('-')[1]) % 12]}</span></span>
                      </div>
                    </td>
                  </tr>
                ),
              ];
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
