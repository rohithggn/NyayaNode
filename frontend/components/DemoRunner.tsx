'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useRouter } from 'next/navigation';

interface DemoStep { id: number; label: string; sublabel: string; route: string; duration: number; color: string; }

const DEMO_STEPS: DemoStep[] = [
  { id:1, label:'Dispute Filed',       sublabel:'Buyer reports damaged ceramic pot · ₹1,240',                          route:'/disputes',  duration:4000, color:'#F59E0B' },
  { id:2, label:'Agent Deployed',      sublabel:'NyayaNode micro-arbitrator activated on ONDC network',                route:'/agent',     duration:3000, color:'#3B82F6' },
  { id:3, label:'Hindsight Rollback',  sublabel:'Settlement rejected · State restored · Alternate path generated',     route:'/agent',     duration:4000, color:'#8B5CF6' },
  { id:4, label:'Cascadeflow Routing', sublabel:'8 tasks → phi-3-mini · 2 tasks → claude-sonnet · ₹0.035 total',      route:'/dashboard', duration:4000, color:'#10B981' },
  { id:5, label:'Verdict Issued',      sublabel:'Full refund ₹1,240 · Logistics liable · Resolved in 4.2s',           route:'/logs',      duration:3000, color:'#10B981' },
];

export default function DemoRunner({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying]     = useState(false);
  const [isDone, setIsDone]           = useState(false);
  const [elapsed, setElapsed]         = useState(0);
  const router      = useRouter();
  const intervalRef = useRef<ReturnType<typeof setInterval>>();
  const elapsedRef  = useRef<ReturnType<typeof setInterval>>();

  function handleStart() { setCurrentStep(0); setIsDone(false); setIsPlaying(true); setElapsed(0); }

  useEffect(() => {
    if (!isPlaying) return;
    clearInterval(intervalRef.current);
    clearInterval(elapsedRef.current);

    router.push(DEMO_STEPS[currentStep].route);

    elapsedRef.current = setInterval(() => setElapsed(e => e + 50), 50);

    const t = setTimeout(() => {
      clearInterval(elapsedRef.current);
      if (currentStep < DEMO_STEPS.length - 1) { setCurrentStep(s => s + 1); setElapsed(0); }
      else { setIsPlaying(false); setIsDone(true); }
    }, DEMO_STEPS[currentStep].duration);

    return () => { clearTimeout(t); clearInterval(elapsedRef.current); clearInterval(intervalRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlaying, currentStep]);

  const step = DEMO_STEPS[currentStep];

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" onClick={onClose}
            initial={{ opacity:0 }} animate={{ opacity:1 }} exit={{ opacity:0 }} />

          <motion.div className="fixed z-50 w-[560px] max-w-[95vw] rounded-2xl p-6 overflow-y-auto"
            style={{ background:'#0D1117', border:'1px solid #1F2937', top:'38%', left:'50%', transform:'translate(-50%,-50%)', maxHeight:'88vh' }}
            initial={{ opacity:0, scale:0.9 }} animate={{ opacity:1, scale:1 }} exit={{ opacity:0, scale:0.9 }}>

            {/* Header */}
            <div className="flex justify-between items-start">
              <div>
                <p className="text-xl font-bold text-white">⚖ NyayaNode Live Demo</p>
                <p className="text-sm mt-1" style={{ color:'#9CA3AF' }}>60-second automated walkthrough · All sponsor tech demonstrated</p>
              </div>
              <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors text-lg leading-none ml-4">✕</button>
            </div>

            {/* Step list */}
            <div className="mt-6 flex flex-col gap-3">
              {DEMO_STEPS.map((s, idx) => {
                const completed = isDone || idx < currentStep;
                const active    = idx === currentStep && isPlaying;
                return (
                  <div key={s.id} className="flex items-center gap-4">
                    <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 ${active ? 'animate-pulse' : ''}`}
                      style={{ background: completed ? 'rgba(16,185,129,0.15)' : active ? `${s.color}22` : '#1F2937',
                               color: completed ? '#10B981' : active ? s.color : '#6B7280' }}>
                      {completed ? '✓' : s.id}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm" style={{ color: active ? s.color : '#F9FAFB' }}>{s.label}</p>
                      <p className="text-xs mt-0.5" style={{ color:'#6B7280' }}>{s.sublabel}</p>
                    </div>
                    {active && (
                      <div className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin flex-shrink-0"
                        style={{ borderColor: `${s.color} transparent transparent transparent` }} />
                    )}
                  </div>
                );
              })}
            </div>

            {/* Progress */}
            <div className="mt-6">
              {isPlaying && (
                <>
                  <p className="text-xs mb-2" style={{ color:'#9CA3AF' }}>Step {currentStep+1} of {DEMO_STEPS.length} · {step.label}</p>
                  <div className="rounded-full h-1.5 w-full" style={{ background:'#1F2937' }}>
                    <motion.div className="h-full rounded-full" style={{ background: step.color, width:`${Math.min((elapsed/step.duration)*100,100)}%` }} transition={{ duration:0.05 }} />
                  </div>
                </>
              )}
              {isDone && <p className="text-sm font-medium text-center" style={{ color:'#10B981' }}>✅ Demo Complete — Dispute resolved in 4.2s for ₹0.035</p>}
            </div>

            {/* Buttons */}
            <div className="mt-6 flex gap-3 justify-end">
              {!isPlaying && !isDone && (
                <button onClick={handleStart} className="px-5 py-2.5 rounded-xl text-sm font-bold hover:brightness-110 transition-all"
                  style={{ background:'#F59E0B', color:'#0A0F1E' }}>▶ Start Demo</button>
              )}
              {isPlaying && (
                <button onClick={() => setIsPlaying(false)} className="px-5 py-2.5 rounded-xl text-sm font-bold transition-all"
                  style={{ background:'#1F2937', color:'#9CA3AF', border:'1px solid #374151' }}>■ Stop</button>
              )}
              {isDone && (
                <>
                  <button onClick={handleStart} className="px-5 py-2.5 rounded-xl text-sm font-bold hover:brightness-110 transition-all"
                    style={{ background:'#F59E0B', color:'#0A0F1E' }}>↺ Replay</button>
                  <button onClick={onClose} className="px-5 py-2.5 rounded-xl text-sm font-bold transition-all"
                    style={{ background:'#1F2937', color:'#9CA3AF', border:'1px solid #374151' }}>Close</button>
                </>
              )}
              {!isDone && (
                <button onClick={onClose} className="text-sm transition-colors hover:text-white px-2" style={{ color:'#6B7280' }}>✕ Cancel</button>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
