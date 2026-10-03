import { Fragment, useMemo, useRef, useState } from 'react';
import { useReveal } from '../lib/anim';
import { useProject, useTwin } from '../lib/store';
import { DIM_HINT, DIM_LABEL, scoreColor } from '../lib/ui';
import Icon from '../components/Icon';
import { RiskBadge, SectionTitle } from '../components/Common';
import { Bar, Radar, Scatter, ScoreRing } from '../components/Charts';
import AIExplain from '../components/AIExplain';

const DIM_ICON: Record<string, string> = { modularity: 'layers', coupling: 'link', complexity: 'twin', maintainability: 'refactor', documentation: 'docs',
  testability: 'check', security: 'shield', performance: 'bolt' };

function fmtMetric(v: any): string {
  if (Array.isArray(v)) return v.length ? v.slice(0, 6).join(', ') + (v.length > 6 ? '…' : '') : '—';
  if (typeof v === 'object' && v) return Object.entries(v).map(([k, x]) => `${k}: ${x}`).join(', ') || '—';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v === 'number') return v % 1 ? v.toFixed(2) : String(v);
  return String(v);
}

export default function Health() {
  const twin = useTwin();
  const { meta, openCode } = useProject();
  const pid = meta!.id;
  const h = twin.health;
  const ref = useRef<HTMLDivElement>(null);
  const [cat, setCat] = useState('all');
  const [sev, setSev] = useState('all');
  useReveal(ref, []);
  const dims = Object.entries(h.dimensions);
  const issues = twin.issues.filter((i) => (cat === 'all' || i.category === cat) && (sev === 'all' || i.severity === sev));
  const cats = ['all', ...Array.from(new Set(twin.issues.map((i) => i.category)))];
  const mods = twin.modules.filter((m) => m.units.length >= 1);
  const seqPoints = useMemo(() => mods.map((m) => ({
    x: m.metrics.instability ?? 0, y: m.metrics.abstractness ?? 0, r: 5 + Math.min(12, Math.sqrt(m.loc) / 3), label: m.name,
    color: (m.metrics.distance ?? 0) > 0.7 ? 'var(--red)' : (m.metrics.distance ?? 0) > 0.4 ? 'var(--orange)' : 'var(--green)',
  })), [twin]);

  return (
    <div className="page" ref={ref}>
      <div className="page-header">
        <div><div className="eyebrow">Measured, not guessed</div><h1 className="h1">Architecture Health</h1>
          <div className="muted" style={{ marginTop: 6 }}>Eight dimensions computed from static analysis. AI only explains them.</div></div>
      </div>
      <div className="grid g3" style={{ marginBottom: 18 }}>
        <div className="card" data-reveal style={{ display: 'grid', placeItems: 'center', textAlign: 'center', padding: 28 }}>
          <ScoreRing value={h.overall} size={210} stroke={18} label="Architecture health" sub={`Grade ${h.grade}`} />
          <div className="small muted" style={{ marginTop: 16, maxWidth: 300 }}>
            Weighted mean of all dimensions. {h.overall >= 80 ? 'Healthy architecture.' : h.overall >= 60 ? 'Sound, with clear areas to improve.' : 'Significant structural risks.'}
          </div>
        </div>
        <div className="card" data-reveal style={{ display: 'grid', placeItems: 'center' }}>
          <Radar data={dims.map(([k, d]) => ({ label: DIM_LABEL[k], value: d.score }))} size={330} />
        </div>
        <div className="card" data-reveal>
          <SectionTitle icon="sparkle" title="What it means" sub="Explanation of the scores" />
          <AIExplain pid={pid} kind="health" payload={{ overall: h.overall, grade: h.grade, dimensions: h.dimensions, debt: { hours: twin.debt.hours, rating: twin.debt.rating },
            cycles: twin.cycles.map((c) => c.map((x) => twin.units[x]?.name)), god_classes: Object.values(twin.units).filter((u) => u.god_class).map((u) => u.name) }} />
        </div>
      </div>

      <div className="grid g4" style={{ marginBottom: 18 }}>
        {dims.map(([k, d]) => (
          <div key={k} className="card" data-reveal>
            <div className="row between">
              <div className="row" style={{ gap: 8 }}><div className="stat-icon" style={{ margin: 0, width: 30, height: 30, background: 'var(--surface-2)', color: scoreColor(d.score) }}><Icon name={DIM_ICON[k]} size={16} /></div><b>{DIM_LABEL[k]}</b></div>
              <span className="num" style={{ fontSize: 26, fontWeight: 700, color: scoreColor(d.score) }}>{d.score}</span>
            </div>
            <div style={{ margin: '10px 0' }}><Bar value={d.score} /></div>
            <div className="small" style={{ minHeight: 40 }}>{d.summary}</div>
            <details style={{ marginTop: 8 }}>
              <summary className="tiny subtle clickable">Evidence · weight {Math.round((h.weights[k] || 0) * 100)}%</summary>
              <div className="tiny subtle" style={{ margin: '6px 0' }}>{DIM_HINT[k]}</div>
              <dl className="kv tiny">{Object.entries(d.metrics).map(([mk, mv]) => <Fragment key={mk}><dt>{mk.replace(/_/g, ' ')}</dt><dd style={{ whiteSpace: 'normal' }}>{fmtMetric(mv)}</dd></Fragment>)}</dl>
            </details>
          </div>
        ))}
      </div>

      <div className="grid g2" style={{ marginBottom: 18 }}>
        <div className="card" data-reveal>
          <SectionTitle icon="map" title="Main sequence (Robert C. Martin)" sub="Instability vs abstractness per module · near the dashed line is balanced" />
          <Scatter points={seqPoints} xLabel="Instability I = Ce / (Ca + Ce)" yLabel="Abstractness A" xMax={1} yMax={1} diagonal />
        </div>
        <div className="card" data-reveal>
          <SectionTitle icon="layers" title="Module coupling metrics" />
          <div style={{ maxHeight: 300, overflow: 'auto' }}>
            <table className="table">
              <thead><tr><th>Module</th><th>Ca</th><th>Ce</th><th>I</th><th>A</th><th>D</th><th>LOC</th></tr></thead>
              <tbody>
                {mods.sort((a, b) => (b.metrics.distance ?? 0) - (a.metrics.distance ?? 0)).map((m) => (
                  <tr key={m.id}><td><b>{m.name}</b> <span className="tiny subtle">{m.app}</span></td><td className="num">{m.metrics.ca}</td><td className="num">{m.metrics.ce}</td>
                    <td className="num">{m.metrics.instability}</td><td className="num">{m.metrics.abstractness}</td>
                    <td className="num" style={{ color: (m.metrics.distance ?? 0) > 0.7 ? 'var(--red)' : undefined }}>{m.metrics.distance}</td><td className="num">{m.loc}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card" data-reveal>
        <SectionTitle icon="alert" title={`Findings · ${twin.issues.length}`} sub="Every finding links to the exact line of code"
          right={<div className="row wrap" style={{ gap: 6 }}>
            {cats.map((c) => <span key={c} className={`chip ${cat === c ? 'active' : ''}`} onClick={() => setCat(c)} style={{ textTransform: 'capitalize' }}>{c}</span>)}
            <select className="select" style={{ width: 130, height: 28, fontSize: 12.5 }} value={sev} onChange={(e) => setSev(e.target.value)}>
              {['all', 'critical', 'high', 'medium', 'low'].map((s) => <option key={s} value={s}>{s === 'all' ? 'All severities' : s}</option>)}
            </select>
          </div>} />
        <table className="table">
          <thead><tr><th>Severity</th><th>Finding</th><th>Location</th><th>Principle</th></tr></thead>
          <tbody>
            {issues.map((i) => (
              <tr key={i.id} className="click" onClick={() => openCode(i.file, i.line)}>
                <td><RiskBadge level={i.severity} /></td>
                <td><b>{i.title}</b><div className="small muted">{i.detail}</div></td>
                <td className="small mono nowrap">{i.file.split('/').pop()}:{i.line}</td>
                <td className="small muted">{i.principle || i.category}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
