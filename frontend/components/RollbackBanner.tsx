'use client';

import { AnimatePresence, motion } from 'framer-motion';

interface RollbackBannerProps {
  visible: boolean;
}

export default function RollbackBanner({ visible }: RollbackBannerProps) {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: -8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: -8 }}
          transition={{ duration: 0.3 }}
        >
          <div
            className="flex items-center gap-4 rounded-xl p-4"
            style={{ background: '#1a0a00', border: '1px solid #d97706' }}
          >
            {/* Left emoji */}
            <span className="text-3xl flex-shrink-0">⏪</span>

            {/* Center text */}
            <div className="flex-1">
              <p className="text-amber-400 font-bold text-sm">HINDSIGHT ROLLBACK ACTIVATED</p>
              <p className="text-xs mt-0.5" style={{ color: 'rgba(253,230,138,0.7)' }}>
                Agent state restored to pre-proposal checkpoint. Generating alternate settlement path...
              </p>
            </div>

            {/* Right pulsing dot */}
            <span className="w-3 h-3 rounded-full bg-amber-400 animate-ping flex-shrink-0" />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
