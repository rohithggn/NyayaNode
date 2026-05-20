import { useEffect, useRef } from 'react';
import { DISPUTE_SCRIPT, type ChatMessage } from '@/lib/agentScripts';

export function useAgentSimulation(
  onMessage: (msg: ChatMessage) => void,
  onRollback: () => void,
  isRunning: boolean,
): void {
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    // Clear any existing timers whenever isRunning changes
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];

    if (!isRunning) return;

    DISPUTE_SCRIPT.forEach((msg, index) => {
      const delay = index * 1800;

      const t = setTimeout(() => {
        onMessage(msg);

        // Index 8 is the ROLLBACK message — fire onRollback 300ms after it appears
        if (index === 8) {
          const rollbackTimer = setTimeout(onRollback, 300);
          timersRef.current.push(rollbackTimer);
        }
      }, delay);

      timersRef.current.push(t);
    });

    return () => {
      timersRef.current.forEach(clearTimeout);
      timersRef.current = [];
    };
  }, [isRunning]); // eslint-disable-line react-hooks/exhaustive-deps
}
