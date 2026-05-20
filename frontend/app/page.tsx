'use client';

import { useState } from 'react';
import { Play, Zap, IndianRupee, Target, TrendingUp, Eye } from 'lucide-react';
import Link from 'next/link';
import CountUp from 'react-countup';
import { disputes } from '@/lib/mockData';
import DemoRunner from '@/components/DemoRunner';

// ─── Stat Pill ────────────────────────────────────────────────────────────────
function StatPill({ icon, label }: { icon: string; label: string }) {
  return (
    <div
      className="flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium"
      style={{
        background: 'rgba(245,158,11,0.08)',
        border: '1px solid rgba(245,158,11,0.25)',
        color: '#F9FAFB',
      }}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </div>
  );
}

// ─── Metric Card ──────────────────────────────────────────────────────────────
function MetricCard({
  label,
  end,
  prefix = '',
  suffix = '',
  decimals = 0,
  sub,
  icon: Icon,
}: {
  label: string;
  end: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  sub?: string;
  icon: React.ElementType;
}) {
  return (
    <div
      className="rounded-xl p-5 flex flex-col gap-3"
      style={{ background: '#111827', border: '1px solid #1F2937' }}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: '#9CA3AF' }}>
          {label}
        </span>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(245,158,11,0.1)' }}>
          <Icon size={16} style={{ color: '#F59E0B' }} />
        </div>
      </div>
      <div>
        <p className="text-2xl font-bold" style={{ color: '#F59E0B' }}>
          <CountUp start={0} end={end} duration={1.5} prefix={prefix} suffix={suffix} decimals={decimals} separator="," useEasing />
        </p>
        {sub && <p className="text-xs mt-1" style={{ color: '#4B5563' }}>{sub}</p>}
      </div>
    </div>
  );
}

// ─── Status Badge ─────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, { bg: string; color: string; border: string }> = {
    Resolved: {
      bg: 'rgba(16,185,129,0.1)',
      color: '#10B981',
      border: 'rgba(16,185,129,0.3)',
    },
    'In Progress': {
      bg: 'rgba(245,158,11,0.1)',
      color: '#F59E0B',
      border: 'rgba(245,158,11,0.3)',
    },
    Escalated: {
      bg: 'rgba(220,38,38,0.1)',
      color: '#DC2626',
      border: 'rgba(220,38,38,0.3)',
    },
  };

  const s = styles[status] ?? styles['In Progress'];

  return (
    <span
      className="px-2.5 py-1 rounded-full text-xs font-semibold"
      style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}
    >
      {status}
    </span>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function HomePage() {
  const [demoOpen, setDemoOpen] = useState(false);

  return (
    <div className="space-y-10 max-w-7xl mx-auto">
      {/* ── Hero ── */}
      <section className="flex flex-col items-center text-center pt-8 pb-4 space-y-6">
        <div className="space-y-3">
          <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight leading-none">
            <span className="gold-gradient">NyayaNode</span>
          </h1>
          <p className="text-base md:text-lg max-w-xl mx-auto leading-relaxed" style={{ color: '#9CA3AF' }}>
            Decentralized AI Arbitration for ONDC &middot; Resolving disputes in seconds, not weeks
          </p>
        </div>

        {/* CTA */}
        <button
          onClick={() => setDemoOpen(true)}
          className="pulse-glow flex items-center gap-3 rounded-xl font-bold text-base transition-all duration-200 hover:scale-105 active:scale-95"
          style={{
            background: '#F59E0B',
            color: '#0A0F1E',
            padding: '16px 40px',
            border: '2px solid #F59E0B',
          }}
        >
          <Play size={18} fill="currentColor" />
          Run Demo
        </button>

        {/* Stat pills */}
        <div className="flex flex-wrap items-center justify-center gap-3">
          <StatPill icon="⚡" label="4.2s avg resolution" />
          <StatPill icon="₹" label="4.87 avg cost" />
          <StatPill icon="🎯" label="94% accuracy" />
        </div>
      </section>

      {/* ── Metrics Grid ── */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: '#4B5563' }}>
          Platform Metrics
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard label="Total Disputes"    end={1247}  sub="All time"        icon={TrendingUp}  />
          <MetricCard label="Resolved Today"    end={38}    sub="Last 24 hours"   icon={Target}      />
          <MetricCard label="Avg Cost / Dispute" end={3.42} prefix="₹" decimals={2} sub="vs ₹180 GPT-4o" icon={IndianRupee} />
          <MetricCard label="Savings vs GPT-4o" end={12840} prefix="₹" sub="This month" icon={Zap} />
        </div>
      </section>

      {/* ── Recent Disputes Table ── */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#4B5563' }}>
            Recent Disputes
          </h2>
          <Link
            href="/disputes"
            className="text-xs font-medium transition-colors hover:underline"
            style={{ color: '#F59E0B' }}
          >
            View all →
          </Link>
        </div>

        <div
          className="rounded-xl overflow-hidden"
          style={{ border: '1px solid #1F2937', background: '#111827' }}
        >
          {/* Table header */}
          <div
            className="hidden md:grid grid-cols-[1fr_1fr_auto_auto_auto_auto] gap-4 px-5 py-3 text-xs font-semibold uppercase tracking-wider"
            style={{ color: '#4B5563', borderBottom: '1px solid #1F2937' }}
          >
            <span>Case ID</span>
            <span>Buyer App</span>
            <span>Amount</span>
            <span>Status</span>
            <span>Resolution</span>
            <span></span>
          </div>

          {/* Rows */}
          {disputes.map((dispute, idx) => (
            <div
              key={dispute.id}
              className="grid grid-cols-1 md:grid-cols-[1fr_1fr_auto_auto_auto_auto] gap-2 md:gap-4 px-5 py-4 items-center transition-colors hover:bg-[#1a2234]"
              style={{
                borderBottom: idx < disputes.length - 1 ? '1px solid #1F2937' : 'none',
              }}
            >
              {/* Case ID */}
              <div>
                <span className="text-xs font-mono" style={{ color: '#9CA3AF' }}>
                  {dispute.id}
                </span>
                {/* Mobile: show category below */}
                <p className="text-xs mt-0.5 md:hidden" style={{ color: '#4B5563' }}>
                  {dispute.category}
                </p>
              </div>

              {/* Buyer App */}
              <div className="flex items-center gap-2">
                <div
                  className="w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold flex-shrink-0"
                  style={{ background: 'rgba(59,130,246,0.15)', color: '#3B82F6' }}
                >
                  {dispute.buyerApp[0]}
                </div>
                <span className="text-sm" style={{ color: '#F9FAFB' }}>
                  {dispute.buyerApp}
                </span>
              </div>

              {/* Amount */}
              <span className="text-sm font-semibold" style={{ color: '#F9FAFB' }}>
                {dispute.amount.toLocaleString('en-IN', {
                  style: 'currency',
                  currency: 'INR',
                  maximumFractionDigits: 0,
                })}
              </span>

              {/* Status */}
              <StatusBadge status={dispute.status} />

              {/* Resolution Time */}
              <span
                className="text-sm font-mono"
                style={{ color: dispute.resolutionTime === '—' ? '#4B5563' : '#10B981' }}
              >
                {dispute.resolutionTime}
              </span>

              {/* Action */}
              <Link
                href="/disputes"
                className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors hover:bg-[#1F2937]"
                style={{ color: '#9CA3AF', border: '1px solid #1F2937' }}
              >
                <Eye size={13} />
                View
              </Link>
            </div>
          ))}
        </div>
      </section>

      <DemoRunner isOpen={demoOpen} onClose={() => setDemoOpen(false)} />
    </div>
  );
}
