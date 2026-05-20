'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import DisputeForm from '@/components/DisputeForm';
import DisputeList from '@/components/DisputeList';
import DisputeTimeline from '@/components/DisputeTimeline';

interface Dispute {
  id: string;
  buyerApp: string;
  sellerApp: string;
  logisticsApp: string;
  amount: number;
  status: 'Resolved' | 'In Progress' | 'Escalated';
  category: string;
  timestamp: string;
  resolutionTime: string;
  complaint: string;
  verdict: string;
}

const MOCK_DISPUTES: Dispute[] = [
  { id: 'NN-2024-001', buyerApp: 'Meesho',      sellerApp: 'Craftsvilla',   logisticsApp: 'Delhivery', amount: 1499, status: 'Resolved',    category: 'Item Not Delivered',  timestamp: '2024-01-15T09:23:00Z', resolutionTime: '3.8s', complaint: 'Order not delivered after 3 days.',          verdict: 'Full refund approved. Delhivery penalised.' },
  { id: 'NN-2024-002', buyerApp: 'Flipkart',     sellerApp: 'TechZone India',logisticsApp: 'Ekart',     amount: 8999, status: 'In Progress', category: 'Wrong Item Received', timestamp: '2024-01-15T11:45:00Z', resolutionTime: '—',    complaint: 'Received wrong item.',                       verdict: 'Awaiting seller response.' },
  { id: 'NN-2024-003', buyerApp: 'Paytm Mall',   sellerApp: 'FashionHub',    logisticsApp: 'BlueDart',  amount: 2250, status: 'Resolved',    category: 'Quality Issue',       timestamp: '2024-01-14T14:10:00Z', resolutionTime: '4.2s', complaint: 'Saree has visible tear.',                    verdict: 'Partial refund of ₹1,125 approved.' },
  { id: 'NN-2024-004', buyerApp: 'Snapdeal',     sellerApp: 'KitchenKing',   logisticsApp: 'DTDC',      amount: 3799, status: 'Escalated',   category: 'Refund Not Processed',timestamp: '2024-01-13T08:30:00Z', resolutionTime: '—',    complaint: 'Refund not credited after 15 days.',         verdict: 'Escalated to ONDC Grievance Cell.' },
  { id: 'NN-2024-005', buyerApp: 'ONDC Ref App', sellerApp: 'OrganicFarms',  logisticsApp: 'Shadowfax', amount: 650,  status: 'Resolved',    category: 'Partial Order',       timestamp: '2024-01-15T07:15:00Z', resolutionTime: '5.1s', complaint: 'Only 3 of 5 items delivered.',               verdict: 'Refund of ₹310 for missing items approved.' },
];

export default function DisputesPage() {
  const [disputes, setDisputes]               = useState<Dispute[]>(MOCK_DISPUTES);
  const [selectedDispute, setSelectedDispute] = useState<Dispute | null>(null);
  const [isTimelineRunning, setIsTimelineRunning] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleNewDispute(data: any) {
    const newDispute: Dispute = { ...data, id: Date.now().toString(), status: 'In Progress' };
    setDisputes(prev => [newDispute, ...prev]);
    setSelectedDispute(newDispute);
    setIsTimelineRunning(true);
  }

  function handleSelect(dispute: Dispute) {
    if (selectedDispute?.id === dispute.id) {
      setSelectedDispute(null);
    } else {
      setSelectedDispute(dispute);
      setIsTimelineRunning(false);
    }
  }

  return (
    <div className="min-h-screen p-6" style={{ background: '#0A0F1E' }}>
      <h2 className="text-2xl font-bold text-white">Dispute Management</h2>
      <p className="text-gray-400 mb-6">File and track ONDC arbitration cases</p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left — Form */}
        <DisputeForm onSubmit={handleNewDispute} />

        {/* Right — List + Timeline */}
        <div className="flex flex-col gap-4">
          <DisputeList
            disputes={disputes}
            selectedId={selectedDispute?.id ?? null}
            onSelect={handleSelect}
          />

          <AnimatePresence>
            {selectedDispute && (
              <motion.div
                key={selectedDispute.id}
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
              >
                <DisputeTimeline
                  isRunning={isTimelineRunning}
                  disputeId={selectedDispute.id}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
