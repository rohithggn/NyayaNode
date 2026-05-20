'use client';

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

interface CostEvent {
  model: string;
  costInr: number;
  taskType: string;
}

interface ModelRouterChartProps {
  events: CostEvent[];
}

const MODEL_COLORS: Record<string, string> = {
  'phi-3-mini':     '#3B82F6',
  'gpt-3.5-turbo':  '#F59E0B',
  'claude-haiku':   '#10B981',
  'claude-sonnet':  '#8B5CF6',
  'gpt-4o':         '#DC2626',
};

export default function ModelRouterChart({ events }: ModelRouterChartProps) {
  // Group by model, sum cost
  const grouped: Record<string, number> = {};
  events.forEach(e => {
    grouped[e.model] = (grouped[e.model] ?? 0) + e.costInr;
  });

  const data = Object.entries(grouped).map(([model, cost]) => ({
    name: model,
    value: parseFloat(cost.toFixed(4)),
  }));

  const maxCost = Math.max(...data.map(d => d.value), 0.0001);

  return (
    <div className="rounded-xl p-6" style={{ background: '#111827', border: '1px solid #1F2937' }}>
      <p className="text-sm font-medium uppercase tracking-widest mb-4" style={{ color: '#9CA3AF' }}>
        Model Usage Distribution
      </p>

      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={85}
            paddingAngle={3}
            dataKey="value"
          >
            {data.map(entry => (
              <Cell key={entry.name} fill={MODEL_COLORS[entry.name] ?? '#6B7280'} />
            ))}
          </Pie>
          <Tooltip
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            formatter={(val: any) => `₹${val}`}
            contentStyle={{
              background: '#111827',
              border: '1px solid #1F2937',
              borderRadius: 8,
              color: '#F9FAFB',
            }}
          />
          <Legend
            iconType="circle"
            formatter={(val: string) => (
              <span style={{ color: '#9CA3AF', fontSize: 12 }}>{val}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>

      {/* Model breakdown list */}
      <div className="flex flex-col gap-3 mt-4">
        {data.map(({ name, value }) => {
          const color = MODEL_COLORS[name] ?? '#6B7280';
          return (
            <div key={name}>
              <div className="flex justify-between items-center mb-1">
                <span className="font-mono text-sm" style={{ color }}>{name}</span>
                <span className="text-sm" style={{ color: '#D1D5DB' }}>₹{value.toFixed(4)}</span>
              </div>
              <div className="rounded h-1.5 w-full" style={{ background: '#1F2937' }}>
                <div
                  className="h-1.5 rounded transition-all duration-500"
                  style={{ width: `${(value / maxCost) * 100}%`, background: color }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
