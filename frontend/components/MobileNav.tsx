'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';

const NAV_LINKS = [
  { label: 'Home',           href: '/'          },
  { label: 'Disputes',       href: '/disputes'  },
  { label: 'Cost Dashboard', href: '/dashboard' },
  { label: 'API Logs',       href: '/logs'      },
];

export default function MobileNav() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();

  return (
    <div className="lg:hidden">
      {/* Fixed top bar */}
      <div
        className="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-4"
        style={{ height: 56, background: '#0D1117', borderBottom: '1px solid #1F2937' }}
      >
        <span className="font-bold text-white text-lg">⚖ NyayaNode</span>

        {/* Hamburger */}
        <button
          onClick={() => setIsOpen(v => !v)}
          className="flex flex-col gap-1 justify-center items-center w-8 h-8"
          aria-label="Toggle menu"
        >
          {[
            { rotate: isOpen ? 45 : 0,  y: isOpen ? 6  : 0 },
            { opacity: isOpen ? 0 : 1                       },
            { rotate: isOpen ? -45 : 0, y: isOpen ? -6 : 0 },
          ].map((anim, i) => (
            <motion.div
              key={i}
              className="w-5 h-0.5 bg-white rounded"
              animate={anim}
              transition={{ duration: 0.2 }}
            />
          ))}
        </button>
      </div>

      {/* Backdrop */}
      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              className="fixed inset-0 z-30 bg-black/50"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
            />
            <motion.div
              className="fixed top-14 left-0 right-0 z-40"
              style={{ background: '#0D1117', borderBottom: '1px solid #1F2937' }}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
            >
              {NAV_LINKS.map(({ label, href }) => {
                const active = pathname === href;
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setIsOpen(false)}
                    className="block py-4 text-sm transition-colors"
                    style={{
                      borderBottom: '1px solid #1F2937',
                      paddingLeft: active ? 20 : 24,
                      borderLeft: active ? '2px solid #F59E0B' : 'none',
                      color: active ? '#F59E0B' : '#9CA3AF',
                      background: 'transparent',
                    }}
                  >
                    {label}
                  </Link>
                );
              })}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
