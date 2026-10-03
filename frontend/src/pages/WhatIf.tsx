import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../lib/api';
import { gsap } from '../lib/anim';
import { useProject, useTwin } from '../lib/store';
import { LAYER_COLORS } from '../lib/ui';
import Icon from '../components/Icon';
import { Empty, LayerTag, NodePicker, SectionTitle, Spinner } from '../components/Common';
import GraphView, { GEdge, GNode } from '../components/GraphView';
import AIExplain from '../components/AIExplain';

const SCENARIOS = [
  { id: 'remove', icon: 'trash', color: '#ff375f', title: 'Remove a component', text: 'What breaks if this module or service disappears?' },
  { id: 'replace', icon: 'refactor', color: '#ff9f0a', title: 'Replace a component', text: 'Which contract must a replacement honour?' },
  { id: 'extract', icon: 'cube', color: '#0a84ff', title: 'Extract a microservice', text: 'Convert one module into a separate service.' },
  { id: 'split', icon: 'split', color: '#bf5af2', title: 'Split the monolith', text: 'Propose service boundaries with community detection.' },
] as const;
const SVC_COLORS = ['#0a84ff', '#bf5af2', '#ff9f0a', '#30d158', '#ff375f', '#5e5ce6', '#40c8e0', '#ffd60a', '#ac8e68'];

export default function WhatIf() {
  const twin = useTwin();
  const { meta, openCode } = useProject();
  const pid = meta!.id;
  const [scenario, setScenario] = useState<string>('split');
  const [target, setTarget] = useState<string | null>(null);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [resolution, setResolution] = useState(1);
  const out = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setRes(null); setErr(null);
    if (scenario === 'extract') setTarget(twin.modules.find((m) => m.name === 'payment')?.id || twin.modules[0]?.id || null);
    else if (scenario !== 'split') setTarget(twin.summary.critical[0] || null);
  }, [scenario]);

  const run = async () => {
    setBusy(true); setErr(null);
    try { setRes(await api.whatif(pid, { scenario, target, resolution })); } catch (e: any) { setErr(e.message); }
    setBusy(false);
  };
  useEffect(() => {
    if (!res || !out.current) return;
    const ctx = gsap.context(() => {
      gsap.fromTo('[data-reveal]', { y: 18, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, stagger: 0.06, ease: 'power3.out' });
    }, out);
    return () => ctx.revert();
  }, [res]);

  const splitGraph = useMemo(() => {
    if (!res || res.scenario !== 'split') return null;
    const nodes: GNode[] = [];
    const svcOf: Record<string, string> = {};
    res.services.forEach((s: any, i: number) => {
      nodes.push({ id: `svc:${s.name}`, label: s.name, color: SVC_COLORS[i % SVC_COLORS.length], isParent: true });
      s.members.forEach((m: any) => { svcOf[m.id] = s.name; nodes.push({ id: m.id, label: m.name, color: LAYER_COLORS[m.layer] || '#8e8e93', parent: `svc:${s.name}`, size: 22 }); });
    });
    const edges: GEdge[] = twin.edges.filter((e) => svcOf[e.source] && svcOf[e.target] && e.source !== e.target).map((e) => ({
      id: e.source + '>' + e.target, source: e.source, target: e.target, type: e.type,
      color: svcOf[e.source] !== svcOf[e.target] ? '#ff375f' : undefined, weight: svcOf[e.source] !== svcOf[e.target] ? 3 : 1,
    }));
    return { nodes, edges };
  }, [res, twin]);

  const est = res?.estimates;
  return (
    <div className="page">
      <div className="page-header">
        <div><div className="eyebrow">Future architecture simulation</div><h1 className="h1">What-If Simulator</h1>
          <div className="muted" style={{ marginTop: 6 }}>Simulate architectural decisions on the twin before touching the code.</div></div>
      </div>
      <div className="grid g4" style={{ marginBottom: 18 }}>
        {SCENARIOS.map((s) => (
          <div key={s.id} className={`scenario ${scenario === s.id ? 'active' : ''}`} onClick={() => setScenario(s.id)}>
            <div className="stat-icon" style={{ background: s.color, color: '#fff' }}><Icon name={s.icon} size={18} /></div>
            <div className="h3">{s.title}</div>
            <div className="small muted" style={{ marginTop: 4 }}>{s.text}</div>
          </div>
        ))}
      </div>

      <div className="card row wrap" style={{ marginBottom: 18, gap: 12, alignItems: 'flex-end' }}>
        {scenario === 'split' ? (
          <div className="grow">
            <label className="label">Granularity (Louvain resolution: higher = more, smaller services) — {resolution.toFixed(1)}</label>
            <input type="range" min={0.5} max={2} step={0.1} value={resolution} onChange={(e) => setResolution(Number(e.target.value))} style={{ width: '100%', accentColor: 'var(--blue)' }} />
          </div>
        ) : (
          <div className="grow" style={{ minWidth: 280 }}>
            <label className="label">{scenario === 'extract' ? 'Module to extract' : 'Component'}</label>
            <NodePicker twin={twin} value={target} onChange={setTarget} kinds={scenario === 'extract' ? ['module'] : ['unit']} />
          </div>
        )}
        <button className="btn btn-primary btn-lg" style={{ height: 40 }} onClick={run} disabled={busy || (scenario !== 'split' && !target)}>
          {busy ? <Spinner /> : <Icon name="bolt" size={16} />}Run simulation
        </button>
      </div>
      {err && <div className="callout danger" style={{ marginBottom: 18 }}>{err}</div>}
      {!res && !busy && <div className="card"><Empty icon="whatif" title="Choose a scenario and run the simulation">Results are computed on the dependency graph, data ownership and transaction boundaries.</Empty></div>}

      {res && (
        <div ref={out}>
          {(res.verdict || res.readiness !== undefined) && (
            <div className="grid g4" style={{ marginBottom: 18 }}>
              <div className="card" data-reveal style={{ background: 'var(--grad)', color: '#fff', border: 0 }}>
                <div className="eyebrow" style={{ color: 'rgba(255,255,255,.75)' }}>Verdict</div>
                <div className="h2" style={{ marginTop: 6, color: '#fff' }}>{res.verdict || (res.readiness >= 70 ? 'Good candidate' : res.readiness >= 45 ? 'Feasible with preparation' : 'Not ready')}</div>
                {res.readiness !== undefined && <div className="small" style={{ marginTop: 6, opacity: 0.9 }}>Extraction readiness {res.readiness}/100</div>}
              </div>
              {est && <>
                <Tile label={res.scenario === 'split' ? 'Proposed services' : 'New remote operations'} value={res.scenario === 'split' ? est.services : est.new_remote_operations} icon="cube" />
                <Tile label="Added latency (worst path)" value={`+${est.added_latency_ms} ms`} icon="clock" sub={est.performance ? `Performance: ${est.performance}` : undefined} />
                <Tile label="Est. monthly infra cost" value={`$${est.monthly_cost_usd[0]}–${est.monthly_cost_usd[1]}`} icon="debt" sub={`Deployment complexity: ${est.deployment_complexity}`} />
              </>}
              {res.scenario === 'remove' && <>
                <Tile label="Break at compile time" value={res.broken.length} icon="alert" />
                <Tile label="Features affected" value={res.features.length} icon="api" />
                <Tile label="Become dead code" value={res.orphans.length} icon="trash" />
              </>}
              {res.scenario === 'replace' && <>
                <Tile label="Methods to implement" value={res.contract.length} icon="code" />
                <Tile label="HTTP endpoints to keep" value={res.endpoints.length} icon="api" />
                <Tile label="Unused public methods" value={res.unused_public_methods.length} icon="trash" />
              </>}
            </div>
          )}

          {res.scenario === 'split' && splitGraph && (
            <div className="card pad-0" style={{ height: 520, marginBottom: 18 }} data-reveal>
              <div style={{ position: 'absolute', top: 14, left: 18, zIndex: 3 }}>
                <div className="h3">Proposed service boundaries</div>
                <div className="card-sub">{Math.round(res.alignment * 100)}% aligned with current packages · red edges become network calls</div>
              </div>
              <div style={{ position: 'absolute', inset: '62px 0 0 0' }}><GraphView nodes={splitGraph.nodes} edges={splitGraph.edges} /></div>
            </div>
          )}

          {res.scenario === 'split' && (
            <div className="grid g3" style={{ marginBottom: 18 }}>
              {res.services.map((s: any, i: number) => (
                <div key={s.name} className="card" data-reveal style={{ borderTop: `4px solid ${SVC_COLORS[i % SVC_COLORS.length]}` }}>
                  <div className="row between"><div className="h3">{s.name}</div><span className="badge neutral">readiness {s.readiness}</span></div>
                  <div className="small muted" style={{ margin: '4px 0 10px' }}>{s.members.length} components · {s.loc} LOC · cohesion {Math.round(s.cohesion * 100)}%</div>
                  <div className="row wrap" style={{ gap: 4 }}>{s.members.map((m: any) => <span key={m.id} className="chip" style={{ height: 24, fontSize: 11.5 }}><span className="dot" style={{ background: LAYER_COLORS[m.layer] }} />{m.name}</span>)}</div>
                  {s.tables.length > 0 && <div className="small" style={{ marginTop: 10 }}><Icon name="db" size={12} /> {s.tables.join(', ')}</div>}
                  {s.endpoints.length > 0 && <div className="tiny subtle" style={{ marginTop: 6 }}>{s.endpoints.length} endpoints</div>}
                </div>
              ))}
            </div>
          )}

          {res.scenario === 'extract' && (
            <div className="grid g2" style={{ marginBottom: 18 }}>
              <div className="card" data-reveal>
                <SectionTitle icon="cube" title={res.name} sub={`${res.members.length} components · ${res.loc} LOC · cohesion ${Math.round(res.boundary.cohesion * 100)}%`} />
                <div className="row wrap" style={{ gap: 4 }}>{res.members.map((m: any) => <span key={m.id} className="chip" style={{ height: 26 }}><span className="dot" style={{ background: LAYER_COLORS[m.layer] }} />{m.name}</span>)}</div>
                <div className="eyebrow" style={{ margin: '14px 0 6px' }}>Operations other services must call remotely</div>
                {Object.entries(res.boundary.inbound).map(([op, callers]: any) => <div key={op} className="row between small" style={{ padding: '3px 0' }}><span className="mono">{op.includes(' ') ? op : op + '()'}</span><span className="subtle">{callers.join(', ')}</span></div>)}
                {!Object.keys(res.boundary.inbound).length && <div className="small muted">None — fully self-contained.</div>}
                <div className="eyebrow" style={{ margin: '14px 0 6px' }}>Outbound calls the new service makes</div>
                {Object.entries(res.boundary.outbound).slice(0, 10).map(([op, callers]: any) => <div key={op} className="row between small" style={{ padding: '3px 0' }}><span className="mono">{op.includes(' ') ? op : op + '()'}</span><span className="subtle">{callers.join(', ')}</span></div>)}
              </div>
              <div className="card" data-reveal>
                <SectionTitle icon="db" title="Data ownership" />
                {res.boundary.owned_tables.map((t: any) => <div key={t.table} className="row small" style={{ padding: '3px 0' }}><span className="badge low">owned</span>{t.table}</div>)}
                {res.boundary.shared_tables.map((t: any) => <div key={t.table} className="row small" style={{ padding: '3px 0' }}><span className="badge high">shared</span>{t.table} <span className="subtle">— {t.used_outside_by.join(', ')}</span></div>)}
                {res.boundary.distributed_transactions.length > 0 && <>
                  <div className="eyebrow" style={{ margin: '14px 0 6px' }}>Transactions that would span services</div>
                  {res.boundary.distributed_transactions.map((t: string) => <div key={t} className="mono small">{t}</div>)}
                </>}
              </div>
            </div>
          )}

          {res.scenario === 'remove' && (
            <div className="grid g2" style={{ marginBottom: 18 }}>
              <div className="card" data-reveal>
                <SectionTitle icon="alert" title={`Consequences of removing ${res.target.name}`} />
                {res.consequences.map((c: string) => <div key={c} className="issue" style={{ marginBottom: 8 }}><Icon name="alert" size={16} style={{ color: 'var(--orange)', flex: 'none' }} /><span className="small">{c}</span></div>)}
              </div>
              <div className="card" data-reveal>
                <SectionTitle icon="layers" title="Directly broken components" />
                {res.broken.map((b: any) => <div key={b.id} className="list-item" onClick={() => openCode(b.file, b.line)}><LayerTag layer={b.layer} small /><b className="grow">{b.name}</b><span className="small subtle">{b.via}</span></div>)}
                {!res.broken.length && <div className="small muted">Nothing depends on it — safe to delete.</div>}
              </div>
            </div>
          )}

          {res.scenario === 'replace' && (
            <div className="card" style={{ marginBottom: 18 }} data-reveal>
              <SectionTitle icon="code" title={`Contract a replacement for ${res.target.name} must provide`} sub={res.interfaces.length ? `Implements ${res.interfaces.join(', ')} — swap the bean to replace it transparently` : undefined} />
              <table className="table"><thead><tr><th>Method</th><th>Signature</th><th>Called by</th></tr></thead>
                <tbody>{res.contract.map((r: any) => <tr key={r.method}><td><b>{r.method}</b></td><td className="mono small">{r.signature}</td><td className="small">{r.callers.join(', ')}</td></tr>)}</tbody></table>
              <div className="col" style={{ gap: 6, marginTop: 14 }}>{res.consequences.map((c: string) => <div key={c} className="small">• {c}</div>)}</div>
            </div>
          )}

          {(res.benefits || res.risks) && (
            <div className="grid g2" style={{ marginBottom: 18 }}>
              <div className="card" data-reveal>
                <SectionTitle icon="check" title="Benefits" />
                {(res.benefits || []).map((b: string) => <div key={b} className="row small" style={{ padding: '5px 0', alignItems: 'flex-start' }}><Icon name="check" size={15} style={{ color: 'var(--green)', flex: 'none', marginTop: 2 }} />{b}</div>)}
              </div>
              <div className="card" data-reveal>
                <SectionTitle icon="alert" title="Risks" />
                {(res.risks || []).map((b: string) => <div key={b} className="row small" style={{ padding: '5px 0', alignItems: 'flex-start' }}><Icon name="alert" size={15} style={{ color: 'var(--red)', flex: 'none', marginTop: 2 }} />{b}</div>)}
              </div>
            </div>
          )}
          {res.recommended_first_steps && (
            <div className="card" style={{ marginBottom: 18 }} data-reveal>
              <SectionTitle icon="map" title="Recommended migration path" />
              <ol style={{ margin: 0, paddingLeft: 20 }}>{res.recommended_first_steps.map((s: string) => <li key={s} style={{ padding: '3px 0' }}>{s}</li>)}</ol>
            </div>
          )}
          {res.assumptions && <div className="small subtle" style={{ marginBottom: 18 }}>Assumptions: {res.assumptions.join(' · ')}</div>}
          <div className="card" data-reveal>
            <SectionTitle icon="sparkle" title="AI architect's take" />
            <AIExplain pid={pid} kind="whatif" payload={{ ...res, impact: undefined, members: res.members?.map((m: any) => m.name), services: res.services?.map((s: any) => ({ ...s, members: s.members.map((m: any) => m.name) })) }} />
          </div>
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, icon, sub }: { label: string; value: any; icon: string; sub?: string }) {
  return (
    <div className="card" data-reveal>
      <div className="stat-icon" style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}><Icon name={icon} /></div>
      <div className="stat-value" style={{ fontSize: 28 }}>{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="tiny subtle" style={{ marginTop: 4 }}>{sub}</div>}
    </div>
  );
}
