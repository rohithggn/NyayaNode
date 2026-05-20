'use client';

import { useEffect, useRef, useState } from 'react';
import { FileText, Bot, Search, MessageSquare, Gavel, Check } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

type StepState = 'pending' | 'active' | 'completed';

interface StepStatus {
  state: StepState;
  timestamp: string | null;
}

interface DisputeTimelineProps {
  isRunning: boolean;
  disputeId: string;
  onComplete?: () => void;
}

// ─── Stage definitions ────────────────────────────────────────────────────────

const STAGES = [
  { id: 1, title: 'Complaint Filed',   description: 'Dispute registered on ONDC network',               Icon: FileText      },
  { id: 2, title: 'Agent Deployed',    description: 'NyayaNode micro-arbitrator activated',             Icon: Bot           },
  { id: 3, title: 'Evidence Gathered', description: 'Tracking data + photo analyzed via Hindsight',     Icon: Search        },
  { id: 4, title: 'Negotiation',       description: 'Multi-agent settlement dialogue initiated',         Icon: MessageSquare },
  { id: 5, title: 'Verdict Delivered', description: 'Binding decision issued',                          Icon: Gavel         },
];

// Timing: [activateAt, completeAt] in ms
const TIMING: [number, number][] = [
  [0,    0],     // step 1: immediate
  [1500, 3000],  // step 2
  [3000, 5000],  // step 3
  [5000, 8000],  // step 4
  [8000, 10000], // step 5
];

function nowIST(): string {
  return new Date().toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }) + ' IST';
}

function initStatuses(): StepStatus[] {
  return STAGES.map(() => ({ state: 'pending' as StepState, timestamp: null }));
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function DisputeTimeline({ isRunning, disputeId, onComplete }: DisputeTimelineProps) {
  const [statuses, setStatuses] = useState<StepStatus[]>(initStatuses);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Reset whenever disputeId changes or isRunning flips off
  useEffect(() => {
    if (!isRunning) {
      setStatuses(initStatuses());
      return;
    }

    // Clear any previous timers
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    setStatuses(initStatuses());

    STAGES.forEach((_, idx) => {
      const [activateAt, completeAt] = TIMING[idx];

      if (activateAt === 0 && completeAt === 0) {
        // Step 1: complete immediately
        setStatuses(prev => {
          const next = [...prev];
          next[0] = { state: 'completed', timestamp: nowIST() };
          if (STAGES.length > 1) next[1] = { state: 'active', timestamp: null };
          return next;
        });
        return;
      }

      // Activate
      const tActivate = setTimeout(() => {
        setStatuses(prev => {
          const next = [...prev];
          next[idx] = { state: 'active', timestamp: null };
          return next;
        });
      }, activateAt);

      // Complete
      const tComplete = setTimeout(() => {
        setStatuses(prev => {
          const next = [...prev];
          next[idx] = { state: 'completed', timestamp: nowIST() };
          // Activate next step
          if (idx + 1 < STAGES.length) {
            next[idx + 1] = { state: 'active', timestamp: null };
          }
          return next;
        });
        if (idx === STAGES.length - 1) {
          onComplete?.();
        }
      }, completeAt);

      timersRef.current.push(tActivate, tComplete);
    });

    return () => {
      timersRef.current.forEach(clearTimeout);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning, disputeId]);

  return (
    <div className="rounded-xl p-5" style={{ background: '#111827', border: '1px solid #1F2937' }}>
      <p className="text-xs font-semibold uppercase tracking-widest mb-5" style={{ color: '#4B5563' }}>
        Arbitration Timeline — {disputeId}
      </p>

      <div className="flex flex-col">
        {STAGES.map((stage, idx) => {
          const { state, timestamp } = statuses[idx];
          const isLast = idx === STAGES.length - 1;
          const { Icon } = stage;

          return (
            <div key={stage.id} className="flex gap-4">
              {/* Left: icon + connector line */}
              <div className="flex flex-col items-center">
                {/* Icon circle */}
                <div className="relative flex-shrink-0" style={{ width: 36, height: 36 }}>
                  {/* Pulsing ring for active */}
                  {state === 'active' && (
                    <span
                      className="absolute inset-0 rounded-full animate-ping"
                      style={{ background: 'rgba(245,158,11,0.35)' }}
                    />
                  )}
                  <div
                    className="relative w-full h-full rounded-full flex items-center justify-center"
                    style={{
                      background:
                        state === 'completed' ? '#10B981' :
                        state === 'active'    ? '#F59E0B' :
                        '#1F2937',
                      transition: 'background 0.4s',
                    }}
                  >
                    {state === 'completed' ? (
                      <Check size={16} color="#fff" strokeWidth={2.5} />
                    ) : (
                      <Icon
                        size={16}
                        color={state === 'active' ? '#0A0F1E' : '#4B5563'}
                      />
                    )}
                  </div>
                </div>

                {/* Connector line */}
                {!isLast && (
                  <div
                    className="w-0.5 flex-1 my-1"
                    style={{
                      minHeight: 28,
                      background: state === 'completed' ? '#10B981' : '#1F2937',
                      transition: 'background 0.5s',
                    }}
                  />
                )}
              </div>

              {/* Right: text */}
              <div className={`pb-5 ${isLast ? '' : ''}`} style={{ paddingBottom: isLast ? 0 : 8 }}>
                <p
                  className="text-sm font-medium leading-tight"
                  style={{
                    color:
                      state === 'completed' ? '#F9FAFB' :
                      state === 'active'    ? '#F59E0B' :
                      '#4B5563',
                    transition: 'color 0.3s',
                  }}
                >
                  {stage.title}
                </p>
                <p className="text-xs mt-0.5" style={{ color: '#4B5563' }}>
                  {stage.description}
                </p>
                {timestamp && (
                  <p className="text-xs mt-1 font-mono" style={{ color: '#F59E0B' }}>
                    ✓ {timestamp}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
