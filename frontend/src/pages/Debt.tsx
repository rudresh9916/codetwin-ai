import { useMemo, useRef, useState } from 'react';
import { useReveal } from '../lib/anim';
import { useProject, useTwin } from '../lib/store';
import { useRouter } from '../lib/router';
import { RISK_COLORS, modName, short } from '../lib/ui';
import Icon from '../components/Icon';
import { LayerTag, RiskBadge, Segmented, SectionTitle, StatCard } from '../components/Common';
import { Bar, Scatter } from '../components/Charts';
import Treemap from '../components/Treemap';

const CAT_COLOR: Record<string, string> = { complexity: '#ff9f0a', design: '#bf5af2', security: '#ff453a', tests: '#0a84ff', documentation: '#8e8e93',
  duplication: '#5e5ce6', size: '#ac8e68', performance: '#ff375f' };

export default function Debt() {
  const twin = useTwin();
  const { meta, openCode } = useProject();
  const { navigate } = useRouter();
  const pid = meta!.id;
  const ref = useRef<HTMLDivElement>(null);
  const [heat, setHeat] = useState<'debt' | 'risk' | 'complexity'>('debt');
  useReveal(ref, []);
  const d = twin.debt;
  const files = twin.files.filter((f) => f.analyzed && !f.is_test);
  const fileRisk = useMemo(() => {
    const m: Record<string, number> = {};
    Object.values(twin.units).forEach((u) => { m[u.file] = Math.max(m[u.file] || 0, u.risk.score); });
    return m;
  }, [twin]);
  const maxCC = Math.max(1, ...files.map((f) => f.complexity || 0));
  const maxDebt = Math.max(1, ...files.map((f) => f.debt?.minutes || 0));
  const items = files.map((f) => {
    const u = Object.values(twin.units).find((x) => x.file === f.path);
    const h = heat === 'debt' ? Math.sqrt((f.debt?.minutes || 0) / maxDebt) : heat === 'risk' ? Math.max(0, ((fileRisk[f.path] || 0) - 0.25) / 0.75) : Math.sqrt((f.complexity || 0) / maxCC);
    return { id: f.path, group: u ? modName(u.module) : f.path.split('/').slice(-2, -1)[0], label: short(f.path).replace(/\.(java|tsx?|jsx?)$/, ''), value: f.sloc, heat: h,
      tooltip: `${f.sloc} SLOC · complexity ${f.complexity} · debt ${f.debt?.minutes} min${f.churn ? ` · ${f.churn} commits` : ''}\n${(f.debt_reasons || []).slice(0, 3).join('\n')}` };
  });
  const risky = Object.values(twin.units).filter((u) => !u.is_test && u.layer !== 'dto').sort((a, b) => b.risk.score - a.risk.score);
  const hot = (twin.history?.hotspots || []) as any[];
  const catTotal = Object.values(d.by_category).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="page" ref={ref}>
      <div className="page-header">
        <div><div className="eyebrow">Where attention is needed</div><h1 className="h1">Technical Debt & Risk</h1>
          <div className="muted" style={{ marginTop: 6 }}>SQALE-style remediation estimates and a defect-risk model (complexity × change frequency × centrality).</div></div>
      </div>
      <div className="grid g4" style={{ marginBottom: 18 }}>
        <StatCard label="Remediation effort (hours)" value={d.hours} decimals={1} icon="clock" color="#ff9f0a" sub={`≈ ${d.days} developer-days`} />
        <StatCard label="Debt ratio (%)" value={Math.round(d.ratio * 1000) / 10} decimals={1} icon="debt" color="#bf5af2" sub={`SQALE rating ${d.rating} · ${d.level}`} />
        <StatCard label="High-risk components" value={twin.summary.high_risk.length} icon="bug" color="#ff453a" sub="likely to contain future bugs" />
        <StatCard label="Findings" value={twin.issues.length} icon="alert" color="#0a84ff" sub={`${twin.issues.filter((i) => i.category === 'security').length} security`} />
      </div>

      <div className="card" style={{ marginBottom: 18 }} data-reveal>
        <SectionTitle icon="map" title="Technical debt heatmap" sub="Area = lines of code, colour = intensity. Click a tile to open the file."
          right={<Segmented value={heat} onChange={setHeat} options={[{ value: 'debt', label: 'Debt' }, { value: 'risk', label: 'Bug risk' }, { value: 'complexity', label: 'Complexity' }]} />} />
        <Treemap items={items} onClick={(id) => openCode(id)} />
        <div className="row small muted" style={{ marginTop: 10, gap: 8 }}>Low<div style={{ width: 160, height: 8, borderRadius: 99, background: 'linear-gradient(90deg,#30d158,#ffd60a,#ff9f0a,#ff453a)' }} />High</div>
      </div>

      <div className="grid g3" style={{ marginBottom: 18 }}>
        <div className="card span2" data-reveal>
          <SectionTitle icon="bug" title="Risk dashboard" sub="Defect-proneness prediction per component" />
          <div style={{ maxHeight: 460, overflow: 'auto' }}>
            {risky.slice(0, 18).map((u) => (
              <div key={u.id} className="list-item" onClick={() => navigate(`/p/${pid}/twin?node=${encodeURIComponent(u.id)}`)}>
                <span className={`dot ${u.risk.level}`} />
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="row" style={{ gap: 8 }}><b>{u.name}</b><LayerTag layer={u.layer} small /></div>
                  <div className="tiny subtle ellipsis">{u.risk.reasons.join(' · ') || 'No significant risk factors'}</div>
                </div>
                <div style={{ width: 120 }}><Bar value={u.risk.score * 100} color={RISK_COLORS[u.risk.level]} /></div>
                <span className="num small" style={{ width: 28, textAlign: 'right', fontWeight: 700 }}>{Math.round(u.risk.score * 100)}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="col" style={{ gap: 18 }}>
          <div className="card" data-reveal>
            <SectionTitle icon="debt" title="Debt by category" />
            {Object.entries(d.by_category).map(([k, v]) => (
              <div key={k} style={{ marginBottom: 10 }}>
                <div className="row between small"><span style={{ textTransform: 'capitalize' }}>{k}</span><b className="num">{Math.round(v / 60 * 10) / 10} h</b></div>
                <Bar value={(v / catTotal) * 100} color={CAT_COLOR[k] || 'var(--blue)'} />
              </div>
            ))}
          </div>
          <div className="card" data-reveal>
            <SectionTitle icon="target" title="Riskiest files" />
            {d.files.slice(0, 6).map((f: any) => (
              <div key={f.path} className="list-item" style={{ padding: '7px 8px' }} onClick={() => openCode(f.path)}>
                <span className={`dot ${f.level}`} />
                <div className="grow" style={{ minWidth: 0 }}><div className="small ellipsis" style={{ fontWeight: 600 }}>{short(f.path)}</div><div className="tiny subtle ellipsis">{f.reasons.slice(0, 2).join(' · ')}</div></div>
                <span className="tiny num">{f.minutes}m</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {hot.length > 0 && (
        <div className="grid g2">
          <div className="card" data-reveal>
            <SectionTitle icon="history" title="Hotspots" sub="Change frequency × complexity (git history) — bubbles = lines of code" />
            <Scatter points={hot.map((r) => ({ x: r.churn, y: r.complexity, r: 4 + Math.sqrt(r.sloc) / 1.6, label: short(r.path).replace(/\.\w+$/, ''), id: r.path,
              color: r.score_norm > 0.5 ? 'var(--red)' : r.score_norm > 0.2 ? 'var(--orange)' : 'var(--blue)' }))} xLabel="Commits touching the file" yLabel="Cyclomatic complexity" onClick={(id) => openCode(id)} />
          </div>
          <div className="card" data-reveal>
            <SectionTitle icon="link" title="Change coupling" sub="Files that keep changing together (hidden dependencies)" />
            {(twin.history.change_coupling || []).slice(0, 8).map((c: any) => (
              <div key={c.a + c.b} className="row small" style={{ padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
                <span className="ellipsis" style={{ fontWeight: 600 }}>{short(c.a)}</span><Icon name="link" size={13} style={{ color: 'var(--text-3)' }} />
                <span className="ellipsis" style={{ fontWeight: 600 }}>{short(c.b)}</span><div className="grow" />
                <RiskBadge level={c.degree >= 0.6 ? 'high' : c.degree >= 0.35 ? 'medium' : 'low'} label={`${c.together}× · ${Math.round(c.degree * 100)}%`} />
              </div>
            ))}
            {!(twin.history.change_coupling || []).length && <div className="small muted">No co-change patterns detected.</div>}
          </div>
        </div>
      )}
    </div>
  );
}
