import { useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
  CartesianGrid, Cell, ReferenceLine,
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
}

interface CI { estimate: number; lower: number; upper: number; n: number }
interface Significance { test: string; p_value: number | null; chi2?: number }

interface TaskClassification {
  skill_knowledge: string[];
  infrastructure_failure: string[];
  skill_only: {
    n_tasks: number;
    traditional_pass_rate: number;
    ontoskills_pass_rate: number;
    traditional_ci: CI;
    ontoskills_ci: CI;
    significance: Significance;
  };
}

interface Statistics {
  traditional_ci: CI;
  ontoskills_ci: CI;
  significance: Significance;
  task_classification: TaskClassification;
}

interface ComparisonData {
  benchmark: string;
  model: string;
  date: string;
  traditional: Summary;
  ontoskills: Summary;
  statistics: Statistics;
  delta: { pass_rate: number; avg_reward: number; token_efficiency_pct: number | null };
  per_task: TaskResult[];
}

/* ------------------------------------------------------------------ */
/* Embedded data (generated from benchmark results)                    */
/* ------------------------------------------------------------------ */

const DATA: ComparisonData = {
  "benchmark": "skillsbench",
  "model": "glm-5.1",
  "date": "2026-04-28",
  "traditional": {
    "pass_rate": 0.4, "avg_reward": 0.4, "tasks_passed": 4, "total_tasks": 10,
    "avg_input_tokens": 17199, "avg_output_tokens": 7279, "total_cost_usd": 3.97,
    "tasks_partial": 0, "tasks_failed": 6,
  },
  "ontoskills": {
    "pass_rate": 0.5, "avg_reward": 0.52, "tasks_passed": 5, "total_tasks": 10,
    "avg_input_tokens": 14680, "avg_output_tokens": 4709, "total_cost_usd": 2.92,
    "tasks_partial": 1, "tasks_failed": 4,
  },
  "statistics": {
    "traditional_ci": {"estimate": 0.4, "lower": 0.1682, "upper": 0.6873, "n": 10},
    "ontoskills_ci": {"estimate": 0.5, "lower": 0.2366, "upper": 0.7634, "n": 10},
    "significance": {"test": "fisher_exact", "p_value": 1.0},
    "task_classification": {
      "skill_knowledge": ["3d-scan-calc", "exceltable-in-ppt", "offer-letter-generator", "paper-anonymizer", "reserves-at-risk-calc", "travel-planning"],
      "infrastructure_failure": ["fix-visual-stability", "flood-risk-analysis", "gh-repo-analytics", "lab-unit-harmonization"],
      "skill_only": {
        "n_tasks": 6,
        "traditional_pass_rate": 0.6667, "ontoskills_pass_rate": 0.8333,
        "traditional_ci": {"estimate": 0.6667, "lower": 0.3, "upper": 0.9032, "n": 6},
        "ontoskills_ci": {"estimate": 0.8333, "lower": 0.4365, "upper": 0.9699, "n": 6},
        "significance": {"test": "fisher_exact", "p_value": 1.0},
      },
    },
  },
  "delta": {"pass_rate": 0.1, "avg_reward": 0.12, "token_efficiency_pct": 14.65},
  "per_task": [
    {"task_id": "reserves-at-risk-calc", "traditional_reward": 0.0, "ontoskills_reward": 0.2, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "offer-letter-generator", "traditional_reward": 1.0, "ontoskills_reward": 1.0, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "lab-unit-harmonization", "traditional_reward": 0.0, "ontoskills_reward": 0.0, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "travel-planning", "traditional_reward": 1.0, "ontoskills_reward": 1.0, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "paper-anonymizer", "traditional_reward": 0.0, "ontoskills_reward": 1.0, "traditional_passed": false, "ontoskills_passed": true},
    {"task_id": "flood-risk-analysis", "traditional_reward": 0.0, "ontoskills_reward": 0.0, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "3d-scan-calc", "traditional_reward": 1.0, "ontoskills_reward": 1.0, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "exceltable-in-ppt", "traditional_reward": 1.0, "ontoskills_reward": 1.0, "traditional_passed": true, "ontoskills_passed": true},
    {"task_id": "fix-visual-stability", "traditional_reward": 0.0, "ontoskills_reward": 0.0, "traditional_passed": false, "ontoskills_passed": false},
    {"task_id": "gh-repo-analytics", "traditional_reward": 0.0, "ontoskills_reward": 0.0, "traditional_passed": false, "ontoskills_passed": false},
  ],
};

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const INFRA_TASKS = new Set(DATA.statistics.task_classification.infrastructure_failure);

function label(id: string): string {
  return id.length > 18 ? id.slice(0, 16) + '...' : id;
}

function pct(v: number): string {
  return (v * 100).toFixed(1) + '%';
}

function ciStr(ci: CI): string {
  return `${pct(ci.estimate)} (${pct(ci.lower)}–${pct(ci.upper)})`;
}

/* ------------------------------------------------------------------ */
/* Components                                                          */
/* ------------------------------------------------------------------ */

function RewardChart({ filter }: { filter: 'all' | 'skill' }) {
  const tasks = filter === 'skill'
    ? DATA.per_task.filter(t => !INFRA_TASKS.has(t.task_id))
    : DATA.per_task;

  const chartData = tasks.map(t => ({
    name: label(t.task_id),
    Traditional: t.traditional_reward,
    OntoSkills: t.ontoskills_reward,
    infra: INFRA_TASKS.has(t.task_id),
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--sl-color-gray-5)" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="var(--sl-color-gray-4)" />
        <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} stroke="var(--sl-color-gray-4)" />
        <Tooltip
          contentStyle={{
            background: 'var(--sl-color-bg)',
            border: '1px solid var(--sl-color-gray-5)',
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Legend />
        <ReferenceLine y={0.5} stroke="var(--sl-color-gray-5)" strokeDasharray="3 3" />
        <Bar dataKey="Traditional" fill="#6366f1" radius={[2, 2, 0, 0]} />
        <Bar dataKey="OntoSkills" fill="#06b6d4" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function TokenChart() {
  const t = DATA.traditional;
  const o = DATA.ontoskills;
  const chartData = [
    { name: 'Input Tokens', Traditional: Math.round(t.avg_input_tokens), OntoSkills: Math.round(o.avg_input_tokens) },
    { name: 'Output Tokens', Traditional: Math.round(t.avg_output_tokens), OntoSkills: Math.round(o.avg_output_tokens) },
    { name: 'Cost ($)', Traditional: Math.round(t.total_cost_usd * 100) / 100, OntoSkills: Math.round(o.total_cost_usd * 100) / 100 },
  ];

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 20, bottom: 5, left: 80 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--sl-color-gray-5)" />
        <XAxis type="number" tick={{ fontSize: 11 }} stroke="var(--sl-color-gray-4)" />
        <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} stroke="var(--sl-color-gray-4)" />
        <Tooltip
          contentStyle={{
            background: 'var(--sl-color-bg)',
            border: '1px solid var(--sl-color-gray-5)',
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Legend />
        <Bar dataKey="Traditional" fill="#6366f1" radius={[0, 2, 2, 0]} />
        <Bar dataKey="OntoSkills" fill="#06b6d4" radius={[0, 2, 2, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ */
/* Main                                                                */
/* ------------------------------------------------------------------ */

export default function BenchmarkApp() {
  const [filter, setFilter] = useState<'all' | 'skill'>('all');
  const so = DATA.statistics.task_classification.skill_only;

  return (
    <div style={{ maxWidth: 800 }}>
      {/* Summary cards */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 200px', padding: 16, borderRadius: 8, border: '1px solid var(--sl-color-gray-5)', background: 'var(--sl-color-bg)' }}>
          <div style={{ fontSize: 12, color: 'var(--sl-color-gray-3)', marginBottom: 4 }}>Pass Rate</div>
          <div style={{ display: 'flex', gap: 16, alignItems: 'baseline' }}>
            <span style={{ fontSize: 24, fontWeight: 700, color: '#6366f1' }}>{pct(DATA.traditional.pass_rate)}</span>
            <span style={{ fontSize: 14, color: 'var(--sl-color-gray-3)' }}>vs</span>
            <span style={{ fontSize: 24, fontWeight: 700, color: '#06b6d4' }}>{pct(DATA.ontoskills.pass_rate)}</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--sl-color-gray-3)', marginTop: 4 }}>
            95% CI: {ciStr(DATA.statistics.traditional_ci)} vs {ciStr(DATA.statistics.ontoskills_ci)}
          </div>
        </div>
        <div style={{ flex: '1 1 200px', padding: 16, borderRadius: 8, border: '1px solid var(--sl-color-gray-5)', background: 'var(--sl-color-bg)' }}>
          <div style={{ fontSize: 12, color: 'var(--sl-color-gray-3)', marginBottom: 4 }}>Avg Reward</div>
          <div style={{ display: 'flex', gap: 16, alignItems: 'baseline' }}>
            <span style={{ fontSize: 24, fontWeight: 700, color: '#6366f1' }}>{DATA.traditional.avg_reward.toFixed(2)}</span>
            <span style={{ fontSize: 14, color: 'var(--sl-color-gray-3)' }}>vs</span>
            <span style={{ fontSize: 24, fontWeight: 700, color: '#06b6d4' }}>{DATA.ontoskills.avg_reward.toFixed(2)}</span>
          </div>
          <div style={{ fontSize: 11, color: '#06b6d4', marginTop: 4 }}>
            +{pct(DATA.delta.avg_reward)} reward
          </div>
        </div>
        <div style={{ flex: '1 1 200px', padding: 16, borderRadius: 8, border: '1px solid var(--sl-color-gray-5)', background: 'var(--sl-color-bg)' }}>
          <div style={{ fontSize: 12, color: 'var(--sl-color-gray-3)', marginBottom: 4 }}>Token Efficiency</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#06b6d4' }}>
            {DATA.delta.token_efficiency_pct?.toFixed(0) ?? '—'}%
          </div>
          <div style={{ fontSize: 11, color: 'var(--sl-color-gray-3)', marginTop: 4 }}>
            fewer input tokens
          </div>
        </div>
      </div>

      {/* Filter toggle */}
      <div style={{ marginBottom: 16 }}>
        <button
          onClick={() => setFilter('all')}
          style={{
            padding: '4px 12px', borderRadius: 4, border: '1px solid var(--sl-color-gray-5)',
            background: filter === 'all' ? 'var(--sl-color-gray-5)' : 'transparent',
            color: 'var(--sl-color-text)', cursor: 'pointer', fontSize: 12, marginRight: 8,
          }}
        >
          All tasks ({DATA.per_task.length})
        </button>
        <button
          onClick={() => setFilter('skill')}
          style={{
            padding: '4px 12px', borderRadius: 4, border: '1px solid var(--sl-color-gray-5)',
            background: filter === 'skill' ? 'var(--sl-color-gray-5)' : 'transparent',
            color: 'var(--sl-color-text)', cursor: 'pointer', fontSize: 12,
          }}
        >
          Skill-knowledge only ({so.n_tasks})
        </button>
      </div>

      {/* Reward chart */}
      <div style={{ marginBottom: 32 }}>
        <h4 style={{ marginTop: 0, marginBottom: 8 }}>Per-Task Reward</h4>
        <RewardChart filter={filter} />
      </div>

      {/* Token chart */}
      <div style={{ marginBottom: 32 }}>
        <h4 style={{ marginTop: 0, marginBottom: 8 }}>Token Efficiency</h4>
        <TokenChart />
      </div>

      {/* Skill-only stats */}
      <div style={{ padding: 16, borderRadius: 8, border: '1px solid var(--sl-color-gray-5)', background: 'var(--sl-color-bg)', marginBottom: 16 }}>
        <h4 style={{ marginTop: 0 }}>Skill-Knowledge Tasks (excluding infrastructure failures)</h4>
        <p style={{ fontSize: 13, color: 'var(--sl-color-gray-3)' }}>
          Excluding {DATA.statistics.task_classification.infrastructure_failure.length} tasks that
          failed for both modes due to infrastructure issues (timeouts, missing dependencies, auth).
        </p>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--sl-color-gray-5)' }}>
              <th style={{ textAlign: 'left', padding: 8 }}>Metric</th>
              <th style={{ textAlign: 'center', padding: 8, color: '#6366f1' }}>Traditional</th>
              <th style={{ textAlign: 'center', padding: 8, color: '#06b6d4' }}>OntoSkills</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ padding: 8 }}>Pass rate</td>
              <td style={{ textAlign: 'center', padding: 8 }}>{pct(so.traditional_pass_rate)}</td>
              <td style={{ textAlign: 'center', padding: 8, fontWeight: 600 }}>{pct(so.ontoskills_pass_rate)}</td>
            </tr>
            <tr style={{ borderBottom: '1px solid var(--sl-color-gray-5)' }}>
              <td style={{ padding: 8 }}>95% CI</td>
              <td style={{ textAlign: 'center', padding: 8, fontSize: 11 }}>{ciStr(so.traditional_ci)}</td>
              <td style={{ textAlign: 'center', padding: 8, fontSize: 11 }}>{ciStr(so.ontoskills_ci)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Per-task table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--sl-color-gray-5)' }}>
              <th style={{ textAlign: 'left', padding: 8 }}>Task</th>
              <th style={{ textAlign: 'center', padding: 8, color: '#6366f1' }}>Traditional</th>
              <th style={{ textAlign: 'center', padding: 8, color: '#06b6d4' }}>OntoSkills</th>
              <th style={{ textAlign: 'center', padding: 8 }}>Type</th>
            </tr>
          </thead>
          <tbody>
            {DATA.per_task.map(t => (
              <tr key={t.task_id} style={{ borderBottom: '1px solid var(--sl-color-gray-6)' }}>
                <td style={{ padding: 8, fontFamily: 'monospace', fontSize: 12 }}>{t.task_id}</td>
                <td style={{ textAlign: 'center', padding: 8 }}>{t.traditional_reward.toFixed(2)}</td>
                <td style={{ textAlign: 'center', padding: 8 }}>{t.ontoskills_reward.toFixed(2)}</td>
                <td style={{ textAlign: 'center', padding: 8, fontSize: 11, color: 'var(--sl-color-gray-3)' }}>
                  {INFRA_TASKS.has(t.task_id) ? 'infra' : 'skill'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
