export type DisputeStatus = 'Resolved' | 'In Progress' | 'Escalated';
export type DisputeCategory =
  | '📦 Damaged Item'
  | '🚫 Not Delivered'
  | '❌ Wrong Item'
  | '💰 Refund Delay';

export interface TimelineStage {
  id: number;
  title: string;
  description: string;
  icon: string; // icon name key
}

export const timelineStages: TimelineStage[] = [
  { id: 1, title: 'Complaint Filed',    description: 'Dispute registered on ONDC network',                icon: 'FileText'      },
  { id: 2, title: 'Agent Deployed',     description: 'NyayaNode micro-arbitrator activated',              icon: 'Bot'           },
  { id: 3, title: 'Evidence Gathered',  description: 'Tracking data + photo analyzed via Hindsight',      icon: 'Search'        },
  { id: 4, title: 'Negotiation',        description: 'Multi-agent settlement dialogue initiated',          icon: 'MessageSquare' },
  { id: 5, title: 'Verdict Delivered',  description: 'Binding decision issued',                           icon: 'Gavel'         },
];

export interface Dispute {
  id: string;
  buyerApp: string;
  sellerApp: string;
  logisticsApp: string;
  amount: number;
  status: DisputeStatus;
  category: string;
  timestamp: string;
  resolutionTime: string;
  complaint: string;
  verdict: string;
}

export interface AgentScenario {
  id: string;
  title: string;
  description: string;
  steps: string[];
  expectedOutcome: string;
}

export interface CostEvent {
  id: string;
  timestamp: string;
  model: string;
  tokens: number;
  costInr: number;
  disputeId: string;
  stage: string;
}

export const disputes: Dispute[] = [
  {
    id: 'NN-2024-001',
    buyerApp: 'Meesho',
    sellerApp: 'Craftsvilla',
    logisticsApp: 'Delhivery',
    amount: 1499,
    status: 'Resolved',
    category: 'Item Not Delivered',
    timestamp: '2024-01-15T09:23:00Z',
    resolutionTime: '3.8s',
    complaint:
      'Order placed on Jan 10 has not been delivered. Tracking shows "Out for Delivery" since Jan 12. No update for 3 days.',
    verdict:
      'Logistics partner failed SLA. Full refund of ₹1,499 approved. Seller absolved. Delhivery penalised ₹200.',
  },
  {
    id: 'NN-2024-002',
    buyerApp: 'Flipkart',
    sellerApp: 'TechZone India',
    logisticsApp: 'Ekart',
    amount: 8999,
    status: 'In Progress',
    category: 'Wrong Item Received',
    timestamp: '2024-01-15T11:45:00Z',
    resolutionTime: '—',
    complaint:
      'Ordered Samsung Galaxy Buds Pro but received a generic earphone worth ₹299. Product images clearly show the wrong item.',
    verdict: 'Awaiting seller response and image verification from logistics.',
  },
  {
    id: 'NN-2024-003',
    buyerApp: 'Paytm Mall',
    sellerApp: 'FashionHub',
    logisticsApp: 'BlueDart',
    amount: 2250,
    status: 'Resolved',
    category: 'Quality Issue',
    timestamp: '2024-01-14T14:10:00Z',
    resolutionTime: '4.2s',
    complaint:
      'Saree received has a visible tear near the border. Quality is far below what was shown in product listing.',
    verdict:
      'Partial refund of ₹1,125 (50%) approved. Seller must update product listing. Return pickup scheduled.',
  },
  {
    id: 'NN-2024-004',
    buyerApp: 'Snapdeal',
    sellerApp: 'KitchenKing',
    logisticsApp: 'DTDC',
    amount: 3799,
    status: 'Escalated',
    category: 'Refund Not Processed',
    timestamp: '2024-01-13T08:30:00Z',
    resolutionTime: '—',
    complaint:
      'Return was picked up 15 days ago. Seller confirmed receipt but refund of ₹3,799 has not been credited. Multiple follow-ups ignored.',
    verdict: 'Escalated to ONDC Grievance Cell. Seller account flagged for review.',
  },
  {
    id: 'NN-2024-005',
    buyerApp: 'ONDC Ref App',
    sellerApp: 'OrganicFarms',
    logisticsApp: 'Shadowfax',
    amount: 650,
    status: 'Resolved',
    category: 'Partial Order',
    timestamp: '2024-01-15T07:15:00Z',
    resolutionTime: '5.1s',
    complaint:
      'Ordered 5 items in a grocery bundle. Only 3 items were delivered. Missing: Organic Honey 500g and Cold-Pressed Oil 1L.',
    verdict:
      'Refund of ₹310 for missing items approved. Seller to improve packing QC. Logistics cleared.',
  },
];

export const agentScenarios: AgentScenario[] = [
  {
    id: 'SCENARIO-001',
    title: 'Non-Delivery with Logistics Fault',
    description:
      'Buyer claims non-delivery. Logistics tracking shows last update 72+ hours ago. Seller has proof of handover.',
    steps: [
      'Ingest complaint via ONDC IGM API',
      'Query logistics provider for real-time tracking data',
      'Cross-reference seller handover timestamp with logistics pickup log',
      'Apply SLA breach detection (>48h without delivery update)',
      'Generate verdict: logistics at fault',
      'Trigger refund workflow via payment gateway',
      'Notify all parties via ONDC callback',
    ],
    expectedOutcome: 'Full refund to buyer. Logistics penalised per ONDC policy.',
  },
  {
    id: 'SCENARIO-002',
    title: 'Wrong Item — Seller Dispute',
    description:
      'Buyer received wrong item. Seller claims correct item was shipped. Image evidence required.',
    steps: [
      'Receive complaint with buyer-uploaded images',
      'Run image classification model against product catalog',
      'Request seller to submit packing slip and dispatch image',
      'Compare SKU codes from both parties',
      'Determine fault based on evidence weight',
      'Issue proportional refund or replacement order',
    ],
    expectedOutcome: 'Seller at fault if SKU mismatch confirmed. Full refund + return pickup.',
  },
  {
    id: 'SCENARIO-003',
    title: 'Quality Dispute — Partial Refund',
    description:
      'Item received but quality significantly below listing. No return possible (perishable/used).',
    steps: [
      'Validate complaint within 48h window',
      'Assess image evidence for quality deviation',
      'Check seller rating history for repeat quality issues',
      'Apply partial refund formula: (deviation_score × order_value)',
      'Update seller quality score in ONDC registry',
    ],
    expectedOutcome: '30–70% partial refund based on deviation severity.',
  },
];

export type LogLevel = 'success' | 'error' | 'warning';

export interface LogEntry {
  id: string;
  timestamp: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  endpoint: string;
  statusCode: number;
  latencyMs: number;
  disputeId: string | null;
  level: LogLevel;
}

export const apiLogs: LogEntry[] = [
  { id: 'LOG-001', timestamp: '2024-01-15T09:22:58Z', method: 'POST', endpoint: '/api/v1/disputes/ingest', statusCode: 201, latencyMs: 142, disputeId: 'NN-2024-001', level: 'success' },
  { id: 'LOG-002', timestamp: '2024-01-15T09:23:01Z', method: 'GET',  endpoint: '/api/v1/logistics/track/DEL-88291', statusCode: 200, latencyMs: 310, disputeId: 'NN-2024-001', level: 'success' },
  { id: 'LOG-003', timestamp: '2024-01-15T09:23:04Z', method: 'POST', endpoint: '/api/v1/ai/classify', statusCode: 200, latencyMs: 620, disputeId: 'NN-2024-001', level: 'success' },
  { id: 'LOG-004', timestamp: '2024-01-15T09:23:06Z', method: 'POST', endpoint: '/api/v1/ai/analyse-evidence', statusCode: 200, latencyMs: 1840, disputeId: 'NN-2024-001', level: 'warning' },
  { id: 'LOG-005', timestamp: '2024-01-15T09:23:08Z', method: 'POST', endpoint: '/api/v1/ai/verdict', statusCode: 200, latencyMs: 980, disputeId: 'NN-2024-001', level: 'success' },
  { id: 'LOG-006', timestamp: '2024-01-15T09:23:10Z', method: 'POST', endpoint: '/api/v1/payments/refund', statusCode: 201, latencyMs: 455, disputeId: 'NN-2024-001', level: 'success' },
  { id: 'LOG-007', timestamp: '2024-01-15T09:23:12Z', method: 'POST', endpoint: '/api/v1/ondc/callback', statusCode: 200, latencyMs: 230, disputeId: 'NN-2024-001', level: 'success' },
  { id: 'LOG-008', timestamp: '2024-01-15T11:44:50Z', method: 'POST', endpoint: '/api/v1/disputes/ingest', statusCode: 201, latencyMs: 188, disputeId: 'NN-2024-002', level: 'success' },
  { id: 'LOG-009', timestamp: '2024-01-15T11:44:55Z', method: 'GET',  endpoint: '/api/v1/catalog/sku/SAMSUNGBUDS-PRO', statusCode: 404, latencyMs: 95,  disputeId: 'NN-2024-002', level: 'error' },
  { id: 'LOG-010', timestamp: '2024-01-15T11:45:02Z', method: 'POST', endpoint: '/api/v1/ai/classify', statusCode: 200, latencyMs: 710, disputeId: 'NN-2024-002', level: 'success' },
  { id: 'LOG-011', timestamp: '2024-01-15T11:45:10Z', method: 'POST', endpoint: '/api/v1/seller/request-evidence', statusCode: 202, latencyMs: 340, disputeId: 'NN-2024-002', level: 'success' },
  { id: 'LOG-012', timestamp: '2024-01-15T11:45:18Z', method: 'GET',  endpoint: '/api/v1/disputes/NN-2024-002/status', statusCode: 200, latencyMs: 88,  disputeId: 'NN-2024-002', level: 'success' },
  { id: 'LOG-013', timestamp: '2024-01-14T14:09:58Z', method: 'POST', endpoint: '/api/v1/disputes/ingest', statusCode: 500, latencyMs: 2100, disputeId: 'NN-2024-003', level: 'error' },
  { id: 'LOG-014', timestamp: '2024-01-14T14:10:05Z', method: 'POST', endpoint: '/api/v1/disputes/ingest', statusCode: 201, latencyMs: 165, disputeId: 'NN-2024-003', level: 'success' },
  { id: 'LOG-015', timestamp: '2024-01-14T14:10:10Z', method: 'POST', endpoint: '/api/v1/ai/classify', statusCode: 200, latencyMs: 590, disputeId: 'NN-2024-003', level: 'success' },
  { id: 'LOG-016', timestamp: '2024-01-14T14:10:15Z', method: 'POST', endpoint: '/api/v1/ai/analyse-evidence', statusCode: 200, latencyMs: 1320, disputeId: 'NN-2024-003', level: 'warning' },
  { id: 'LOG-017', timestamp: '2024-01-13T08:29:45Z', method: 'POST', endpoint: '/api/v1/disputes/ingest', statusCode: 201, latencyMs: 201, disputeId: 'NN-2024-004', level: 'success' },
  { id: 'LOG-018', timestamp: '2024-01-13T08:30:10Z', method: 'GET',  endpoint: '/api/v1/seller/NN-2024-004/refund-status', statusCode: 503, latencyMs: 4500, disputeId: 'NN-2024-004', level: 'error' },
  { id: 'LOG-019', timestamp: '2024-01-13T08:30:22Z', method: 'POST', endpoint: '/api/v1/ondc/escalate', statusCode: 200, latencyMs: 412, disputeId: 'NN-2024-004', level: 'success' },
  { id: 'LOG-020', timestamp: '2024-01-15T07:15:03Z', method: 'POST', endpoint: '/api/v1/disputes/ingest', statusCode: 201, latencyMs: 155, disputeId: 'NN-2024-005', level: 'success' },
  { id: 'LOG-021', timestamp: '2024-01-15T07:15:08Z', method: 'POST', endpoint: '/api/v1/ai/classify', statusCode: 200, latencyMs: 640, disputeId: 'NN-2024-005', level: 'success' },
  { id: 'LOG-022', timestamp: '2024-01-15T07:15:14Z', method: 'POST', endpoint: '/api/v1/ai/verdict', statusCode: 200, latencyMs: 870, disputeId: 'NN-2024-005', level: 'success' },
  { id: 'LOG-023', timestamp: '2024-01-15T07:15:18Z', method: 'POST', endpoint: '/api/v1/payments/refund', statusCode: 422, latencyMs: 310, disputeId: 'NN-2024-005', level: 'error' },
  { id: 'LOG-024', timestamp: '2024-01-15T07:15:25Z', method: 'POST', endpoint: '/api/v1/payments/refund', statusCode: 201, latencyMs: 290, disputeId: 'NN-2024-005', level: 'success' },
];

export const costEventLog: CostEvent[] = [
  {
    id: 'CE-001',
    timestamp: '2024-01-15T09:23:04Z',
    model: 'Gemini Flash 1.5',
    tokens: 1240,
    costInr: 0.62,
    disputeId: 'NN-2024-001',
    stage: 'Initial Classification',
  },
  {
    id: 'CE-002',
    timestamp: '2024-01-15T09:23:06Z',
    model: 'Gemini Flash 1.5',
    tokens: 3800,
    costInr: 1.90,
    disputeId: 'NN-2024-001',
    stage: 'Evidence Analysis',
  },
  {
    id: 'CE-003',
    timestamp: '2024-01-15T09:23:08Z',
    model: 'Gemini Flash 1.5',
    tokens: 2100,
    costInr: 1.05,
    disputeId: 'NN-2024-001',
    stage: 'Verdict Generation',
  },
  {
    id: 'CE-004',
    timestamp: '2024-01-14T14:10:05Z',
    model: 'Gemini Flash 1.5',
    tokens: 4200,
    costInr: 2.10,
    disputeId: 'NN-2024-003',
    stage: 'Full Resolution',
  },
  {
    id: 'CE-005',
    timestamp: '2024-01-15T07:15:03Z',
    model: 'Gemini Flash 1.5',
    tokens: 2800,
    costInr: 1.40,
    disputeId: 'NN-2024-005',
    stage: 'Full Resolution',
  },
];
