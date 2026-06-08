import React from 'react';
import { Sankey, Tooltip, Layer, Rectangle, ResponsiveContainer } from 'recharts';
import type { PipelineResult } from '../types';
import { Card } from '../ui';
import { money } from '../format';

const STATUS_COLORS: Record<string, string> = {
  'Reconciled': 'var(--status-ok)',
  'Immaterial break': 'var(--status-immaterial)',
  'Material break': 'var(--status-material)',
  'GL only': 'var(--status-orphan)',
  'TB only': 'var(--status-orphan)',
};

function nodeColor(name: string): string {
  if (name === 'GL Postings') return '#0F0B0B';
  if (STATUS_COLORS[name]) return STATUS_COLORS[name];
  return '#86BC24';
}

const SankeyNode = (props: any) => {
  const { x, y, width, height, payload } = props;
  // status nodes are the rightmost layer -> label on their left, others on right
  const isRight = !!STATUS_COLORS[payload.name];
  const color = nodeColor(payload.name);
  return (
    <Layer>
      <Rectangle x={x} y={y} width={width} height={height} fill={color} fillOpacity={0.95} radius={[2, 2, 2, 2]} />
      <text
        textAnchor={isRight ? 'end' : 'start'}
        x={isRight ? x - 8 : x + width + 8}
        y={y + height / 2}
        dy="0.34em"
        fontSize={11}
        fontWeight={600}
        fill="var(--ink)"
      >
        {payload.name}
      </text>
    </Layer>
  );
};

const SankeyLink = (props: any) => {
  const { sourceX, sourceY, sourceControlX, targetControlX, targetX, targetY, linkWidth, index } = props;
  return (
    <path
      d={`M${sourceX},${sourceY}C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
      stroke="#86BC24"
      strokeWidth={Math.max(linkWidth, 1)}
      strokeOpacity={0.22}
      fill="none"
      key={index}
    />
  );
};

const FlowSankey: React.FC<{ result: PipelineResult }> = ({ result }) => {
  const data = result.sankey;
  const hasFlow = data && data.links && data.links.length > 0;

  return (
    <Card title="Transaction-flow lineage"
      subtitle="GL postings → account category → reconciliation status (width = balance weight)">
      {hasFlow ? (
        <div style={{ height: 340 }}>
          <ResponsiveContainer width="100%" height="100%">
            <Sankey
              data={data}
              nodePadding={22}
              nodeWidth={12}
              margin={{ top: 12, bottom: 12, left: 70, right: 90 }}
              link={<SankeyLink />}
              node={<SankeyNode />}
            >
              <Tooltip
                formatter={(v: any) => money(Number(v))}
                contentStyle={{ borderRadius: 10, border: '1px solid var(--border)', fontSize: 12 }}
              />
            </Sankey>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="text-sm text-[var(--muted)] py-10 text-center">No reconciliation flow to display.</div>
      )}
    </Card>
  );
};

export default FlowSankey;
