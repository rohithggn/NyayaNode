'use client';

import { useCallback, useState } from 'react';
import AgentChat from '@/components/AgentChat';
import RollbackBanner from '@/components/RollbackBanner';
import { useAgentSimulation } from '@/hooks/useTypewriter';
import type { ChatMessage } from '@/lib/agentScripts';

export default function AgentPage() {
  const [messages, setMessages]         = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning]       = useState(false);
  const [showRollback, setShowRollback] = useState(false);
  const [isDimmed, setIsDimmed]         = useState(false);

  const handleMessage = useCallback((msg: ChatMessage) => {
    setMessages(prev => [...prev, msg]);
  }, []);

  const handleRollback = useCallback(() => {
    setShowRollback(true);
    setIsDimmed(true);
    setTimeout(() => {
      setIsDimmed(false);
      setShowRollback(false);
    }, 3000);
  }, []);

  const handleStart = useCallback(() => {
    setMessages([]);
    setShowRollback(false);
    setIsDimmed(false);
    setIsRunning(false);
    setTimeout(() => setIsRunning(true), 100);
  }, []);

  useAgentSimulation(handleMessage, handleRollback, isRunning);

  const totalCost   = messages.reduce((s, m) => s + m.costInr, 0);
  const uniqueModels = new Set(messages.map(m => m.model)).size;

  return (
    <div className="min-h-screen p-6" style={{ background: '#0A0F1E' }}>
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div>
          <h2 className="text-2xl font-bold text-white">Live Agent Negotiation</h2>
          <p className="text-gray-400 text-sm mt-0.5">
            Multi-agent arbitration powered by Hindsight state management
          </p>
        </div>
        <div className="flex items-center gap-3 mt-1">
          {isRunning ? (
            <>
              <span className="text-amber-400 text-sm font-medium animate-pulse flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
                Negotiating...
              </span>
              <button
                onClick={() => { setIsRunning(false); setMessages([]); }}
                className="px-4 py-2 rounded-lg text-sm font-medium transition-all hover:brightness-110"
                style={{ background: '#1F2937', color: '#9CA3AF', border: '1px solid #374151' }}
              >
                ↺ Reset
              </button>
            </>
          ) : (
            <button
              onClick={handleStart}
              className="px-5 py-2.5 rounded-xl text-sm font-bold transition-all hover:scale-[1.02] hover:brightness-110"
              style={{ background: '#F59E0B', color: '#0A0F1E' }}
            >
              ▶ Start Negotiation
            </button>
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-3 mt-4 mb-3 flex-wrap">
        <span className="text-amber-400   bg-[#1a1500] border border-amber-900   rounded-full px-3 py-1 text-xs">⚖ Arbitrator</span>
        <span className="text-blue-400    bg-[#0d1a2e] border border-blue-900    rounded-full px-3 py-1 text-xs">🛒 Buyer Agent</span>
        <span className="text-emerald-400 bg-[#0d1f15] border border-emerald-900 rounded-full px-3 py-1 text-xs">🏪 Seller Agent</span>
      </div>

      {/* Rollback banner */}
      <div className="mt-3 mb-3">
        <RollbackBanner visible={showRollback} />
      </div>

      {/* Agent chat */}
      <AgentChat messages={messages} isRunning={isRunning} isDimmed={isDimmed} />

      {/* Stats bar */}
      <div className="mt-4 grid grid-cols-3 gap-4">
        {[
          { label: 'Messages Exchanged', value: messages.length,            color: 'text-amber-400'   },
          { label: 'Total Cost',         value: `₹${totalCost.toFixed(3)}`, color: 'text-emerald-400' },
          { label: 'Models Used',        value: `${uniqueModels} unique`,   color: 'text-blue-400'    },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-xl p-4" style={{ background: '#111827', border: '1px solid #1F2937' }}>
            <p className="text-xs font-medium uppercase tracking-wider mb-2" style={{ color: '#4B5563' }}>{label}</p>
            <p className={`text-2xl font-bold ${color}`}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
