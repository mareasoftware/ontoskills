import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  CartesianGrid, LabelList,
} from 'recharts';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface TaskResult {
  task_id: string;
  traditional_reward: number;
  ontoskills_reward: number;
  traditional_passed: boolean;
  ontoskills_passed: boolean;
}

interface Summary {
  pass_rate: number;
  avg_reward: number;
  tasks_passed: number;
  total_tasks: number;
  avg_input_tokens: number;
  avg_output_tokens: number;
  total_cost_usd: number;
  tasks_partial?: number;
  tasks_failed?: number;
}

interface ComparisonData {
  benchmark: string;
  model: string;
  date: string;
  traditional: Summary;
  ontoskills: Summary;
  per_task: TaskResult[];
}

/* ------------------------------------------------------------------ */
/* Embedded data                                                       */
/* ------------------------------------------------------------------ */

const DATA: ComparisonData = {
  "benchmark": "skillsbench",
  "model": "glm-5.1",
  "date": "2026-04-29",
  "traditional": {
    "pass_rate": 0.50, "avg_reward": 0.562, "tasks_passed": 12, "total_tasks": 24,
    "avg_input_tokens": 18950, "avg_output_tokens": 5623, "total_cost_usd": 11.53,
    "tasks_partial": 4, "tasks_failed": 8,
  },
  "ontoskills": {
    "pass_rate": 0.375, "avg_reward": 0.489, "tasks_passed": 9, "total_tasks": 24,
    "avg_input_tokens": 16845, "avg_output_tokens": 5236, "total_cost_usd": 10.38,
    "tasks_partial": 6, "tasks_failed": 9,
  },
  "per_task": [
    {"task_id": "3d-scan-calc", "traditional_reward": 1.000, "ontoskills_reward": 1.000, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "adaptive-cruise-control", "traditional_reward": 0.083, "ontoskills_reward": 0.083, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "earthquake-plate-calculation", "traditional_reward": 1.000, "ontoskills_reward": 1.000, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "energy-ac-optimal-power-flow", "traditional_reward": 0.000, "ontoskills_reward": 0.000, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "exceltable-in-ppt", "traditional_reward": 1.000, "ontoskills_reward": 1.000, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "exoplanet-detection-period", "traditional_reward": 1.000, "ontoskills_reward": 1.000, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "fix-visual-stability", "traditional_reward": 0.000, "ontoskills_reward": 0.000, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "flink-query", "traditional_reward": 0.000, "ontoskills_reward": 0.000, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "flood-risk-analysis", "traditional_reward": 1.000, "ontoskills_reward": 0.000, "traditional_passed": true, "ontoskills_passed": false},
    {"task_id": "gh-repo-analytics", "traditional_reward": 0.250, "ontoskills_reward": 0.000, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "hvac-control", "traditional_reward": 1.000, "ontoskills_reward": 0.000, "traditional_passed": true, "ontoskills_passed": false},
    {"task_id": "jax-computing-basics", "traditional_reward": 1.000, "ontoskills_reward": 1.000, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "lab-unit-harmonization", "traditional_reward": 0.000, "ontoskills_reward": 0.000, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "lake-warming-attribution", "traditional_reward": 1.000, "ontoskills_reward": 0.000, "traditional_passed": true, "ontoskills_passed": false},
    {"task_id": "mario-coin-counting", "traditional_reward": 1.000, "ontoskills_reward": 1.000, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "mars-clouds-clustering", "traditional_reward": 0.000, "ontoskills_reward": 1.000, "traditional_passed": false, "ontoskills_passed": true},
    {"task_id": "offer-letter-generator", "traditional_reward": 1.000, "ontoskills_reward": 1.000, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "paper-anonymizer", "traditional_reward": 1.000, "ontoskills_reward": 0.500, "traditional_passed": true, "ontoskills_passed": false},
    {"task_id": "pg-essay-to-audiobook", "traditional_reward": 0.750, "ontoskills_reward": 0.750, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "reserves-at-risk-calc", "traditional_reward": 0.000, "ontoskills_reward": 0.000, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "sec-financial-report", "traditional_reward": 0.000, "ontoskills_reward": 0.500, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "seismic-phase-picking", "traditional_reward": 0.000, "ontoskills_reward": 0.500, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "shock-analysis-demand", "traditional_reward": 0.400, "ontoskills_reward": 0.400, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "travel-planning", "traditional_reward": 1.000, "ontoskills_reward": 1.000, "traditional_passed": true, "ontoskills_passed": true},
  ],
};

/* ------------------------------------------------------------------ */
/* Model pricing                                                       */
/* ------------------------------------------------------------------ */

interface ModelPrice {
  label: string;
  input: number;   // $/MTok
  output: number;  // $/MTok
  used: boolean;   // true = the model actually ran the benchmark
}

const MODELS: Record<string, ModelPrice> = {
  "glm-5.1":        { label: "GLM-5.1",         input: 1.40, output: 4.40, used: true },
  "glm-5":          { label: "GLM-5",            input: 1.00, output: 3.20, used: false },
  "glm-5-turbo":    { label: "GLM-5 Turbo",      input: 1.20, output: 4.00, used: false },
  "glm-4.7":        { label: "GLM-4.7",          input: 0.60, output: 2.20, used: false },
  "claude-opus":    { label: "Claude Opus 4.7",   input: 15.00, output: 75.00, used: false },
  "claude-sonnet":  { label: "Claude Sonnet 4.6", input: 3.00, output: 15.00, used: false },
  "claude-haiku":   { label: "Claude Haiku 4.5",  input: 0.80, output: 4.00, used: false },
  "gpt-5.4":        { label: "GPT-5.4",           input: 2.50, output: 15.00, used: false },
  "gpt-5.4-mini":   { label: "GPT-5.4 mini",      input: 0.75, output: 4.50, used: false },
};

const TOTAL_INPUT_TRAD = DATA.traditional.total_tasks * DATA.traditional.avg_input_tokens;
const TOTAL_OUTPUT_TRAD = DATA.traditional.total_tasks * DATA.traditional.avg_output_tokens;
const TOTAL_INPUT_ONTO = DATA.ontoskills.total_tasks * DATA.ontoskills.avg_input_tokens;
const TOTAL_OUTPUT_ONTO = DATA.ontoskills.total_tasks * DATA.ontoskills.avg_output_tokens;

function modelCost(m: ModelPrice, mode: 'traditional' | 'ontoskills'): number {
  const inp = mode === 'traditional' ? TOTAL_INPUT_TRAD : TOTAL_INPUT_ONTO;
  const out = mode === 'traditional' ? TOTAL_OUTPUT_TRAD : TOTAL_OUTPUT_ONTO;
  return (inp * m.input + out * m.output) / 1_000_000;
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const TRAD = '#9763e1';  // --accent-purple
const ONTO = '#52c7e8';  // --accent-cyan
const PASS = '#85f496';  // --accent-mint
const PARTIAL = '#fbbf24';
const FAIL = '#6b7280';

function rewardCell(v: number) {
  if (v >= 1.0) return <span style={{ color: PASS, fontWeight: 700, fontSize: 13 }}>PASS</span>;
  if (v > 0) return <span style={{ color: PARTIAL, fontWeight: 700, fontSize: 13 }}>{(v * 100).toFixed(0)}%</span>;
  return <span style={{ color: FAIL, fontSize: 13 }}>-</span>;
}

function fmtTok(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/* ------------------------------------------------------------------ */
/* Section wrapper                                                     */
/* ------------------------------------------------------------------ */

function Section({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <div style={{
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border)',
      borderRadius: 12,
      padding: 24,
      marginBottom: 24,
      overflow: 'hidden',
      minWidth: 0,
    }}>
      <h3 style={{ marginTop: 0, marginBottom: note ? 4 : 16, fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
        {title}
      </h3>
      {note && <p style={{ marginTop: 0, marginBottom: 16, fontSize: 12, color: 'var(--text-muted)' }}>{note}</p>}
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Per-task chart                                                      */
/* ------------------------------------------------------------------ */

function RewardChart() {
  const chartData = DATA.per_task.map(t => ({
    name: t.task_id.length > 16 ? t.task_id.slice(0, 14) + '...' : t.task_id,
    Traditional: t.traditional_reward,
    OntoSkills: t.ontoskills_reward,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} margin={{ top: 28, right: 12, bottom: 48, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
          stroke="rgba(255,255,255,0.06)"
          angle={-40}
          textAnchor="end"
          interval={0}
        />
        <YAxis
          domain={[0, 1]}
          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          stroke="rgba(255,255,255,0.06)"
          tickFormatter={v => `${(v * 100).toFixed(0)}%`}
          width={40}
        />
        <Tooltip
          formatter={(value: number | undefined, name: string) => [
            `${((value ?? 0) * 100).toFixed(0)}%`,
            name,
          ]}
          contentStyle={{
            background: '#1a1a1a',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 8,
            fontSize: 12,
            color: '#f5f5f5',
          }}
          itemStyle={{ color: '#f5f5f5' }}
        />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        <Bar dataKey="Traditional" fill={TRAD} radius={[3, 3, 0, 0]} maxBarSize={28}>
          <LabelList dataKey="Traditional" position="top" fontSize={10} fontWeight={600}
            fill="var(--text-muted)"
            formatter={(v: number | string) => !v || v === 0 ? '' : `${(Number(v) * 100).toFixed(0)}%`}
          />
        </Bar>
        <Bar dataKey="OntoSkills" fill={ONTO} radius={[3, 3, 0, 0]} maxBarSize={28}>
          <LabelList dataKey="OntoSkills" position="top" fontSize={10} fontWeight={600}
            fill="var(--text-muted)"
            formatter={(v: number | string) => !v || v === 0 ? '' : `${(Number(v) * 100).toFixed(0)}%`}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

export default function BenchmarkApp() {
  const t = DATA.traditional;
  const o = DATA.ontoskills;
  const deltaReward = o.avg_reward - t.avg_reward;
  const deltaTokenPct = (((t.avg_input_tokens + t.avg_output_tokens) - (o.avg_input_tokens + o.avg_output_tokens)) / (t.avg_input_tokens + t.avg_output_tokens) * 100);

  const totalTasks = t.total_tasks;
  const tradPassed = DATA.per_task.filter(x => x.traditional_passed).length;
  const ontoPassed = DATA.per_task.filter(x => x.ontoskills_passed).length;
  const ontoOnly = DATA.per_task.filter(x => x.ontoskills_passed && !x.traditional_passed).length;

  return (
    <div style={{ width: '100%', minWidth: 0 }}>

      {/* -- Headline metrics -- */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, marginBottom: 28 }}>
        {[
          {
            label: 'Avg Score',
            trad: `${(t.avg_reward * 100).toFixed(0)}%`,
            onto: `${(o.avg_reward * 100).toFixed(0)}%`,
            delta: deltaReward > 0 ? `+${(deltaReward * 100).toFixed(0)}pp` : undefined,
          },
          {
            label: 'Pass Rate',
            trad: `${(t.pass_rate * 100).toFixed(0)}%`,
            onto: `${(o.pass_rate * 100).toFixed(0)}%`,
            delta: o.pass_rate > t.pass_rate ? `+${((o.pass_rate - t.pass_rate) * 100).toFixed(0)}pp` : undefined,
          },
          {
            label: 'Tokens / Task',
            trad: fmtTok(t.avg_input_tokens + t.avg_output_tokens),
            onto: fmtTok(o.avg_input_tokens + o.avg_output_tokens),
            delta: deltaTokenPct > 0 ? `-${deltaTokenPct.toFixed(0)}%` : undefined,
          },
          {
            label: `Cost (${DATA.model})`,
            trad: `$${t.total_cost_usd.toFixed(2)}`,
            onto: `$${o.total_cost_usd.toFixed(2)}`,
            delta: t.total_cost_usd > 0 ? `-${((t.total_cost_usd - o.total_cost_usd) / t.total_cost_usd * 100).toFixed(0)}%` : undefined,
          },
        ].map(m => (
          <div key={m.label} style={{
            padding: '14px 16px', borderRadius: 10,
            border: '1px solid var(--border)', background: 'var(--bg-elevated)',
          }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 }}>
              {m.label}
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontSize: 20, fontWeight: 700, color: TRAD, fontFamily: "'JetBrains Mono', monospace" }}>{m.trad}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>vs</span>
              <span style={{ fontSize: 20, fontWeight: 700, color: ONTO, fontFamily: "'JetBrains Mono', monospace" }}>{m.onto}</span>
              {m.delta && (
                <span style={{ fontSize: 11, color: PASS, fontWeight: 600, marginLeft: 2 }}>{m.delta}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* -- Insight banner -- */}
      {ontoOnly > 0 && (
        <div style={{
          padding: '12px 20px', borderRadius: 10, marginBottom: 24,
          background: 'rgba(82,199,232,0.06)',
          border: '1px solid rgba(82,199,232,0.15)',
          fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6,
        }}>
          OntoSkills solved <strong style={{ color: ONTO }}>{ontoOnly} task{ontoOnly > 1 ? 's' : ''}</strong> that Traditional failed
          ({DATA.per_task.filter(x => x.ontoskills_passed && !x.traditional_passed).map(x => x.task_id).join(', ')}).
          {ontoPassed > tradPassed && ` Overall, OntoSkills passed ${ontoPassed}/${totalTasks} vs ${tradPassed}/${totalTasks}.`}
        </div>
      )}

      {/* -- Per-task chart -- */}
      <Section title="Per-Task Score" note="Score = tests passed / tests total. Evaluated via Docker + pytest (deterministic).">
        <RewardChart />
      </Section>

      {/* -- Token usage -- */}
      <Section title="Token Usage" note={`Per-task averages measured from ${DATA.model} benchmark (${totalTasks} tasks, seed=7). OntoSkills uses MCP tool calls instead of reading full markdown files.`}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
          {[
            { label: 'Input Tokens / Task', trad: t.avg_input_tokens, onto: o.avg_input_tokens },
            { label: 'Output Tokens / Task', trad: t.avg_output_tokens, onto: o.avg_output_tokens },
            { label: 'Total Tokens / Task', trad: t.avg_input_tokens + t.avg_output_tokens, onto: o.avg_input_tokens + o.avg_output_tokens },
          ].map(row => {
            const diff = ((row.trad - row.onto) / row.trad * 100);
            return (
              <div key={row.label} style={{
                padding: '12px 16px', borderRadius: 8,
                border: '1px solid var(--border)', background: 'rgba(255,255,255,0.02)',
              }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 6 }}>
                  {row.label}
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 14, fontFamily: "'JetBrains Mono', monospace" }}>
                  <span style={{ color: TRAD, fontWeight: 600 }}>{fmtTok(row.trad)}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>vs</span>
                  <span style={{ color: ONTO, fontWeight: 600 }}>{fmtTok(row.onto)}</span>
                  {diff > 0 && <span style={{ color: PASS, fontSize: 11, fontWeight: 600 }}>-{diff.toFixed(0)}%</span>}
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      {/* -- Cost comparison table -- */}
      <Section
        title="Estimated Cost by Model"
        note={`Token usage measured from ${DATA.model} benchmark (${totalTasks} tasks, seed=7). Costs for other models are extrapolated from the same token counts — they did not run the benchmark. Savings = (Traditional cost - OntoSkills cost) / Traditional cost.`}
      >
        <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 560 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--border)' }}>
              <th style={{ textAlign: 'left', padding: '8px 8px', fontWeight: 600 }}>Model</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11 }}>Input $/MTok</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600, color: 'var(--text-muted)', fontSize: 11 }}>Output $/MTok</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600, color: TRAD }}>Traditional</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600, color: ONTO }}>OntoSkills</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', fontWeight: 600 }}>Savings</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(MODELS).map(([id, m]) => {
              const tradCost = modelCost(m, 'traditional');
              const ontoCost = modelCost(m, 'ontoskills');
              const savings = ((tradCost - ontoCost) / tradCost * 100);
              return (
                <tr key={id} style={{
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  background: m.used ? 'rgba(82,199,232,0.05)' : 'transparent',
                }}>
                  <td style={{ padding: '8px 8px', fontWeight: m.used ? 600 : 400 }}>
                    {m.label}
                    {m.used && <span style={{ fontSize: 9, marginLeft: 6, color: ONTO, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>actual</span>}
                  </td>
                  <td style={{ padding: '8px 8px', textAlign: 'right', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                    ${m.input.toFixed(2)}
                  </td>
                  <td style={{ padding: '8px 8px', textAlign: 'right', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                    ${m.output.toFixed(2)}
                  </td>
                  <td style={{ padding: '8px 8px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", color: TRAD }}>
                    ${tradCost.toFixed(2)}
                  </td>
                  <td style={{ padding: '8px 8px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", color: ONTO }}>
                    ${ontoCost.toFixed(2)}
                  </td>
                  <td style={{
                    padding: '8px 8px', textAlign: 'right', fontWeight: 600,
                    color: savings > 0 ? PASS : FAIL,
                    fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
                  }}>
                    {savings > 0 ? '-' : '+'}{Math.abs(savings).toFixed(0)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </Section>

      {/* -- Per-task detail table -- */}
      <Section title="Task Results">
        <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 420 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--border)' }}>
              <th style={{ textAlign: 'left', padding: '8px 8px', fontWeight: 600 }}>Task</th>
              <th style={{ textAlign: 'center', padding: '8px 8px', fontWeight: 600, color: TRAD, minWidth: 80 }}>Traditional</th>
              <th style={{ textAlign: 'center', padding: '8px 8px', fontWeight: 600, color: ONTO, minWidth: 80 }}>OntoSkills</th>
              <th style={{ textAlign: 'center', padding: '8px 8px', fontWeight: 600, minWidth: 60 }}>Delta</th>
            </tr>
          </thead>
          <tbody>
            {DATA.per_task.map(t => {
              const delta = t.ontoskills_reward - t.traditional_reward;
              return (
                <tr key={t.task_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '8px 8px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>
                    {t.task_id}
                  </td>
                  <td style={{ textAlign: 'center', padding: '8px 8px' }}>{rewardCell(t.traditional_reward)}</td>
                  <td style={{ textAlign: 'center', padding: '8px 8px' }}>{rewardCell(t.ontoskills_reward)}</td>
                  <td style={{ textAlign: 'center', padding: '8px 8px', fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
                    color: delta > 0 ? PASS : delta < 0 ? '#f87171' : 'var(--text-muted)',
                    fontWeight: delta !== 0 ? 600 : 400,
                  }}>
                    {delta > 0 ? '+' : ''}{delta > 0 ? `${(delta * 100).toFixed(0)}%` : delta < 0 ? `${(delta * 100).toFixed(0)}%` : '-'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </Section>
    </div>
  );
}
