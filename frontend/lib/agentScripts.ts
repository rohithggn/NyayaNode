export type AgentRole = 'arbitrator' | 'buyer' | 'seller';

export interface ChatMessage {
  id: string;
  role: AgentRole;
  text: string;
  model: string;
  costInr: number;
  timestamp: string;
}

// IST timestamps starting at 14:33:01, incrementing by 3–8s each message
const TIMESTAMPS = [
  '14:33:01 IST',
  '14:33:06 IST',
  '14:33:12 IST',
  '14:33:18 IST',
  '14:33:24 IST',
  '14:33:30 IST',
  '14:33:37 IST',
  '14:33:43 IST',
  '14:33:49 IST',
  '14:33:56 IST',
  '14:34:02 IST',
  '14:34:08 IST',
];

const RAW: Omit<ChatMessage, 'id' | 'timestamp'>[] = [
  { role: 'arbitrator', model: 'gpt-3.5-turbo',  costInr: 0.002, text: 'Dispute #NYA-2847 received. Buyer reports damaged item. Initiating evidence collection protocol.' },
  { role: 'buyer',      model: 'phi-3-mini',      costInr: 0.001, text: 'I received a completely broken ceramic pot. The packaging was crushed. I have photo evidence ready.' },
  { role: 'seller',     model: 'phi-3-mini',      costInr: 0.001, text: 'Our records show the item was packed per ONDC standard S-4.2. Requesting logistics scan data.' },
  { role: 'arbitrator', model: 'gpt-3.5-turbo',  costInr: 0.003, text: "Querying Delhivery tracking API... Last scan: 'Impact event detected — Bhiwandi hub, 14:32 IST'. Logging as World Fact in Hindsight." },
  { role: 'buyer',      model: 'phi-3-mini',      costInr: 0.001, text: 'That confirms it was damaged in transit, not at origin. I want a full refund of ₹1,240.' },
  { role: 'seller',     model: 'phi-3-mini',      costInr: 0.001, text: 'We accept the logistics data. However we request 40% cost sharing with logistics provider.' },
  { role: 'arbitrator', model: 'claude-haiku',    costInr: 0.004, text: 'Generating settlement proposal A: Full refund ₹1,240 split 60% logistics / 40% seller. Presenting to parties.' },
  { role: 'seller',     model: 'phi-3-mini',      costInr: 0.001, text: 'Rejected. We cannot accept more than 25% liability without further evidence of improper handling.' },
  { role: 'arbitrator', model: 'claude-haiku',    costInr: 0.004, text: '⚠ Proposal rejected. Initiating Hindsight ROLLBACK — restoring state to pre-proposal checkpoint. Generating alternate path.' },
  { role: 'arbitrator', model: 'claude-sonnet',   costInr: 0.018, text: 'Escalating to high-reasoning model. New proposal B: Full refund from logistics provider. Seller receives ONDC dispute credit.' },
  { role: 'seller',     model: 'phi-3-mini',      costInr: 0.001, text: 'Proposal B accepted. ONDC credit is acceptable compensation.' },
  { role: 'arbitrator', model: 'claude-sonnet',   costInr: 0.018, text: '✅ VERDICT: Full refund ₹1,240 issued to buyer. Logistics provider liable. Case closed in 4.2s.' },
];

export const DISPUTE_SCRIPT: ChatMessage[] = RAW.map((msg, i) => ({
  ...msg,
  id: `msg-${i + 1}`,
  timestamp: TIMESTAMPS[i],
}));
