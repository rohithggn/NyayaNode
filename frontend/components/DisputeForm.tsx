'use client';

import { useRef, useState } from 'react';
import { CloudUpload, X } from 'lucide-react';
import type { Dispute, DisputeStatus } from '@/lib/mockData';

// ─── Types ────────────────────────────────────────────────────────────────────

interface DisputeFormProps {
  onSubmit: (dispute: Dispute) => void;
}

type Category = '📦 Damaged Item' | '🚫 Not Delivered' | '❌ Wrong Item' | '💰 Refund Delay';

interface FormState {
  buyerApp: string;
  sellerApp: string;
  logisticsApp: string;
  amount: string;
  category: Category | '';
  complaint: string;
}

interface FormErrors {
  buyerApp?: string;
  sellerApp?: string;
  logisticsApp?: string;
  amount?: string;
  category?: string;
  complaint?: string;
}

// ─── Options ──────────────────────────────────────────────────────────────────

const BUYER_APPS   = ['Meesho', 'Paytm Mall', 'Snapdeal', 'PhonePe Commerce', 'ONDC Ref App'];
const SELLER_APPS  = ['Dukaan', 'Bikayi', 'eSamudaay', 'StoreHippo', 'GoFrugal'];
const LOGISTICS    = ['Dunzo', 'Shadowfax', 'Shiprocket', 'Delhivery', 'Porter'];
const CATEGORIES: Category[] = ['📦 Damaged Item', '🚫 Not Delivered', '❌ Wrong Item', '💰 Refund Delay'];

// ─── Helpers ──────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: '#0D1117',
  border: '1px solid #374151',
  color: '#F9FAFB',
  borderRadius: 8,
  padding: '10px 16px',
  width: '100%',
  fontSize: 14,
  outline: 'none',
};

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 12,
  fontWeight: 500,
  color: '#9CA3AF',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginBottom: 6,
};

let disputeCounter = 6;

function generateId(): string {
  return `NN-2024-00${disputeCounter++}`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function DisputeForm({ onSubmit }: DisputeFormProps) {
  const [form, setForm] = useState<FormState>({
    buyerApp: '', sellerApp: '', logisticsApp: '',
    amount: '', category: '', complaint: '',
  });
  const [errors, setErrors]       = useState<FormErrors>({});
  const [preview, setPreview]     = useState<string | null>(null);
  const [dragging, setDragging]   = useState(false);
  const fileRef                   = useRef<HTMLInputElement>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(prev => ({ ...prev, [key]: value }));
    setErrors(prev => ({ ...prev, [key]: undefined }));
  }

  function handleFile(file: File | undefined) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => setPreview(e.target?.result as string);
    reader.readAsDataURL(file);
  }

  function validate(): boolean {
    const e: FormErrors = {};
    if (!form.buyerApp)    e.buyerApp    = 'Buyer App is required';
    if (!form.sellerApp)   e.sellerApp   = 'Seller App is required';
    if (!form.logisticsApp) e.logisticsApp = 'Logistics Partner is required';
    if (!form.amount || isNaN(Number(form.amount)) || Number(form.amount) <= 0)
      e.amount = 'Enter a valid amount';
    if (!form.category)    e.category    = 'Select a dispute category';
    if (!form.complaint.trim()) e.complaint = 'Complaint description is required';
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    const newDispute: Dispute = {
      id: generateId(),
      buyerApp: form.buyerApp,
      sellerApp: form.sellerApp,
      logisticsApp: form.logisticsApp,
      amount: Number(form.amount),
      status: 'In Progress' as DisputeStatus,
      category: form.category,
      timestamp: new Date().toISOString(),
      resolutionTime: '—',
      complaint: form.complaint,
      verdict: 'Pending arbitration.',
    };

    onSubmit(newDispute);
    setForm({ buyerApp: '', sellerApp: '', logisticsApp: '', amount: '', category: '', complaint: '' });
    setPreview(null);
    setErrors({});
  }

  return (
    <div className="rounded-xl p-6" style={{ background: '#111827', border: '1px solid #1F2937' }}>
      <h2 className="text-base font-bold mb-5" style={{ color: '#F9FAFB' }}>⚖ File a Dispute</h2>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>

        {/* Buyer App */}
        <div>
          <label style={labelStyle}>Buyer App</label>
          <select value={form.buyerApp} onChange={e => set('buyerApp', e.target.value)} style={inputStyle}>
            <option value="">Select buyer app…</option>
            {BUYER_APPS.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          {errors.buyerApp && <p className="text-xs mt-1" style={{ color: '#DC2626' }}>{errors.buyerApp}</p>}
        </div>

        {/* Seller App */}
        <div>
          <label style={labelStyle}>Seller App</label>
          <select value={form.sellerApp} onChange={e => set('sellerApp', e.target.value)} style={inputStyle}>
            <option value="">Select seller app…</option>
            {SELLER_APPS.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          {errors.sellerApp && <p className="text-xs mt-1" style={{ color: '#DC2626' }}>{errors.sellerApp}</p>}
        </div>

        {/* Logistics */}
        <div>
          <label style={labelStyle}>Logistics Partner</label>
          <select value={form.logisticsApp} onChange={e => set('logisticsApp', e.target.value)} style={inputStyle}>
            <option value="">Select logistics partner…</option>
            {LOGISTICS.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          {errors.logisticsApp && <p className="text-xs mt-1" style={{ color: '#DC2626' }}>{errors.logisticsApp}</p>}
        </div>

        {/* Amount */}
        <div>
          <label style={labelStyle}>Order Amount</label>
          <div className="relative">
            <span
              className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-semibold pointer-events-none"
              style={{ color: '#9CA3AF' }}
            >₹</span>
            <input
              type="number"
              min="1"
              placeholder="Enter amount in ₹"
              value={form.amount}
              onChange={e => set('amount', e.target.value)}
              style={{ ...inputStyle, paddingLeft: 28 }}
            />
          </div>
          {errors.amount && <p className="text-xs mt-1" style={{ color: '#DC2626' }}>{errors.amount}</p>}
        </div>

        {/* Category pills */}
        <div>
          <label style={labelStyle}>Dispute Category</label>
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map(cat => {
              const active = form.category === cat;
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() => set('category', cat)}
                  className="px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-150"
                  style={{
                    background: active ? 'rgba(245,158,11,0.12)' : '#0D1117',
                    border: active ? '1px solid #F59E0B' : '1px solid #374151',
                    color: active ? '#F59E0B' : '#6B7280',
                  }}
                >
                  {cat}
                </button>
              );
            })}
          </div>
          {errors.category && <p className="text-xs mt-1" style={{ color: '#DC2626' }}>{errors.category}</p>}
        </div>

        {/* Complaint */}
        <div>
          <label style={labelStyle}>Complaint Description</label>
          <textarea
            rows={4}
            placeholder="Describe the issue in detail…"
            value={form.complaint}
            onChange={e => set('complaint', e.target.value)}
            style={{ ...inputStyle, resize: 'vertical' }}
          />
          {errors.complaint && <p className="text-xs mt-1" style={{ color: '#DC2626' }}>{errors.complaint}</p>}
        </div>

        {/* File upload */}
        <div>
          <label style={labelStyle}>Evidence Photo</label>
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={e => {
              e.preventDefault();
              setDragging(false);
              handleFile(e.dataTransfer.files[0]);
            }}
            className="rounded-lg flex flex-col items-center justify-center gap-2 cursor-pointer transition-colors"
            style={{
              background: '#0D1117',
              border: `2px dashed ${dragging ? '#F59E0B' : 'rgba(245,158,11,0.35)'}`,
              padding: '20px 16px',
            }}
          >
            {preview ? (
              <div className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={preview} alt="Evidence preview" className="rounded-lg object-cover" style={{ width: 100, height: 100 }} />
                <button
                  type="button"
                  onClick={e => { e.stopPropagation(); setPreview(null); }}
                  className="absolute -top-2 -right-2 w-5 h-5 rounded-full flex items-center justify-center"
                  style={{ background: '#DC2626' }}
                >
                  <X size={11} color="#fff" />
                </button>
              </div>
            ) : (
              <>
                <CloudUpload size={24} style={{ color: 'rgba(245,158,11,0.6)' }} />
                <p className="text-xs text-center" style={{ color: '#6B7280' }}>
                  Drop photo here or <span style={{ color: '#F59E0B' }}>click to upload</span>
                </p>
              </>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={e => handleFile(e.target.files?.[0])}
          />
        </div>

        {/* Submit */}
        <button
          type="submit"
          className="w-full rounded-xl py-3 font-bold text-sm transition-all duration-150 hover:scale-[1.02] hover:brightness-110 active:scale-95"
          style={{ background: '#F59E0B', color: '#0A0F1E' }}
        >
          ⚖ Submit for Arbitration
        </button>
      </form>
    </div>
  );
}
