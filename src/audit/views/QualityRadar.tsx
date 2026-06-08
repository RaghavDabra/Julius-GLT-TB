import React from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip,
} from 'recharts';
import type { PipelineResult } from '../types';
import { DIMENSIONS, scoreColor } from '../format';
import { Card } from '../ui';

const QualityRadar: React.FC<{ result: PipelineResult }> = ({ result }) => {
  const data = DIMENSIONS.map((d) => ({
    dimension: d.charAt(0).toUpperCase() + d.slice(1),
    score: Math.round((result.scorecard[d] as number) * 100),
  }));

  return (
    <Card title="Data-quality scorecard" subtitle="Six assurance dimensions (0–100)">
      <div className="flex flex-col sm:flex-row items-center gap-4">
        <div className="w-full sm:w-3/5" style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={data} outerRadius="72%">
              <PolarGrid stroke="rgba(15,11,11,0.10)" />
              <PolarAngleAxis dataKey="dimension" tick={{ fill: 'var(--muted)', fontSize: 11 }} />
              <PolarRadiusAxis domain={[0, 100]} tick={{ fill: 'var(--faint)', fontSize: 9 }} angle={30} />
              <Radar dataKey="score" stroke="#86BC24" fill="#86BC24" fillOpacity={0.32} strokeWidth={2} />
              <Tooltip formatter={(v: any) => [`${v}%`, 'Score']}
                contentStyle={{ borderRadius: 10, border: '1px solid var(--border)', fontSize: 12 }} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
        <div className="w-full sm:w-2/5 space-y-2">
          {data.map((d) => {
            const raw = d.score / 100;
            return (
              <div key={d.dimension}>
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-[var(--muted)]">{d.dimension}</span>
                  <span className="font-semibold" style={{ color: scoreColor(raw) }}>{d.score}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-[rgba(15,11,11,0.06)] overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${d.score}%`, background: scoreColor(raw) }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
};

export default QualityRadar;
