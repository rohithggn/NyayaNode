'use client';

import { useEffect, useRef } from 'react';

type AgentRole = 'arbitrator' | 'buyer' | 'seller';

interface ChatMessage {
  id: string;
  role: AgentRole;
  text: string;
  model: string;
  costInr: number;
  timestamp: string;
}

interface AgentChatProps {
  messages: ChatMessage[];
  isRunning: boolean;
  isDimmed?: boolean;
}

const AGENT_CONFIG: Record<AgentRole, { label: string; color: string; bgCard: string; borderColor: string }> = {
  arbitrator: { label: '⚖ Arbitrator',   color: 'text-amber-400',   bgCard: 'bg-[#1a1500]', borderColor: 'border-amber-900'   },
  buyer:      { label: '🛒 Buyer Agent',  color: 'text-blue-400',    bgCard: 'bg-[#0d1a2e]', borderColor: 'border-blue-900'    },
  seller:     { label: '🏪 Seller Agent', color: 'text-emerald-400', bgCard: 'bg-[#0d1f15]', borderColor: 'border-emerald-900' },
};

const ROLES: AgentRole[] = ['arbitrator', 'buyer', 'seller'];

function AgentColumn({
  role, messages, isRunning, isDimmed,
}: {
  role: AgentRole; messages: ChatMessage[]; isRunning: boolean; isDimmed: boolean;
}) {
  const cfg       = AGENT_CONFIG[role];
  const scrollRef = useRef<HTMLDivElement>(null);
  const colMsgs   = messages.filter(m => m.role === role);

  // Find index of rollback message in the full messages array
  const rollbackGlobalIdx = messages.findIndex(m => m.text.includes('ROLLBACK'));

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [colMsgs.length]);

  return (
    <div className="flex flex-col">
      <p className={`font-semibold text-sm pb-2 mb-3 border-b border-[#1F2937] ${cfg.color}`}>
        {cfg.label}
      </p>

      <div ref={scrollRef} className="flex flex-col gap-2 overflow-y-auto" style={{ maxHeight: 380 }}>
        {isRunning && colMsgs.length === 0 ? (
          <div className="flex flex-col gap-2 animate-pulse">
            <div className="h-3 rounded bg-[#1F2937] w-3/4" />
            <div className="h-3 rounded bg-[#1F2937] w-full" />
            <div className="h-3 rounded bg-[#1F2937] w-1/2" />
          </div>
        ) : (
          colMsgs.map(msg => {
            const globalIdx = messages.findIndex(m => m.id === msg.id);
            const dimmed = isDimmed && rollbackGlobalIdx !== -1 && globalIdx < rollbackGlobalIdx;
            return (
              <div
                key={msg.id}
                className={`rounded-lg p-3 border ${cfg.bgCard} ${cfg.borderColor}`}
                style={dimmed ? { opacity: 0.35, filter: 'grayscale(1)' } : undefined}
              >
                <p className="text-sm text-white leading-relaxed mb-2">{msg.text}</p>
                <div className="flex items-center gap-2">
                  <span className="bg-[#1F2937] text-gray-400 text-xs px-2 py-0.5 rounded font-mono">
                    {msg.model}
                  </span>
                  <span className="text-xs text-gray-500">₹{msg.costInr.toFixed(3)}</span>
                  <span className="text-xs text-gray-600 ml-auto">{msg.timestamp}</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default function AgentChat({ messages, isRunning, isDimmed = false }: AgentChatProps) {
  return (
    <div className="bg-[#0D1117] rounded-xl border border-[#1F2937] p-4">
      <div className="grid grid-cols-3 gap-3">
        {ROLES.map(role => (
          <AgentColumn key={role} role={role} messages={messages} isRunning={isRunning} isDimmed={isDimmed} />
        ))}
      </div>
    </div>
  );
}
