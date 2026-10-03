import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../lib/api';
import { gsap } from '../lib/anim';
import { useProject, useTwin } from '../lib/store';
import { useRouter } from '../lib/router';
import { LAYER_COLORS, modName } from '../lib/ui';
import Icon from '../components/Icon';
import { Empty, LayerTag, NodePicker, Segmented, SectionTitle, Spinner } from '../components/Common';
import GraphView, { GEdge, GNode } from '../components/GraphView';
import AIExplain from '../components/AIExplain';

export default function Impact() {
  const twin = useTwin();
  const { meta, openCode } = useProject();
  const { loc, navigate } = useRouter();
  const pid = meta!.id;
  const [target, setTarget] = useState<string | null>(loc.query.get('target') || twin.summary.high_risk[0] || twin.summary.critical[0] || null);
  const [change, setChange] = useState<'modify' | 'signature' | 'remove'>('modify');
  const [method, setMethod] = useState('');
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const out = useRef<HTMLDivElement>(null);
  const unit = target ? twin.units[target] : null;

  const run = async (t = target) => {
    if (!t) return;
    setBusy(true); setErr(null);
    try {
      const r = await api.impact(pid, { target: t, change, method: change === 'signature' ? method : undefined });
      setRes(r);
      navigate(`/p/${pid}/impact?target=${encodeURIComponent(t)}`, true);
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  };
  useEffect(() => { if (loc.query.get('target')) run(loc.query.get('target')); }, []);
  useEffect(() => {
    if (!res || !out.current) return;
    const ctx = gsap.context(() => {
      gsap.fromTo('.risk-hero', { y: 20, opacity: 0, scale: 0.98 }, { y: 0, opacity: 1, scale: 1, duration: 0.7, ease: 'power3.out' });
      gsap.fromTo('.chain .node, .chain .arr', { x: -12, opacity: 0 }, { x: 0, opacity: 1, duration: 0.4, stagger: 0.06, delay: 0.3, ease: 'power2.out' });
      gsap.fromTo('[data-reveal]', { y: 14, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55, stagger: 0.05, delay: 0.2, ease: 'power3.out' });
      gsap.fromTo('.risk-score', { textContent: 0 }, { textContent: res.risk.score, duration: 1.1, ease: 'power2.out', snap: { textContent: 1 } });
    }, out);
    return () => ctx.revert();
  }, [res]);

  const sub = useMemo(() => {
    if (!res) return null;
    const ids = new Set<string>([res.target.id, ...res.affected.map((a: any) => a.id), ...res.endpoints.map((a: any) => a.id), ...res.data.map((d: any) => d.id)]);
    const dist: Record<string, number> = { [res.target.id]: 0 };
    [...res.affected, ...res.endpoints].forEach((a: any) => { dist[a.id] = a.distance; });
    res.data.forEach((d: any) => { dist[d.id] = 1; });
    const nodes: GNode[] = [...ids].map((id) => {
      const layer = twin.units[id]?.layer || (twin.endpoints[id] ? 'endpoint' : twin.tables[id] ? 'table' : 'module');
      const name = twin.units[id]?.name || (twin.endpoints[id] ? `${twin.endpoints[id].method} ${twin.endpoints[id].path}` : twin.tables[id]?.name || id);
      return { id, label: name, color: LAYER_COLORS[layer] || '#8e8e93', size: id === res.target.id ? 46 : 30, kind: layer === 'endpoint' ? 'endpoint' : layer === 'table' ? 'table' : '' };
    });
    const edges: GEdge[] = twin.edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ id: e.source + '>' + e.target, source: e.source, target: e.target, type: e.types.includes('http') ? 'http' : e.type }));
    return { nodes, edges, dist };
  }, [res, twin]);

  const groups = useMemo(() => {
    if (!res) return [];
    const g: Record<string, any[]> = {};
    res.affected.forEach((a: any) => { (g[a.likelihood] = g[a.likelihood] || []).push(a); });
    return ['direct', 'indirect', 'transitive', 'possible'].filter((k) => g[k]).map((k) => [k, g[k]] as [string, any[]]);
  }, [res]);

  return (
    <div className="page">
      <div className="page-header">
        <div><div className="eyebrow">Dependency-based change propagation</div><h1 className="h1">Change Impact Analysis</h1>
          <div className="muted" style={{ marginTop: 6 }}>“If I modify this, what will break?” — computed on the twin's dependency graph, explained by AI.</div></div>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="grid impact-form" style={{ gap: 12, alignItems: 'end' }}>
          <div><label className="label">Component, endpoint or table</label><NodePicker twin={twin} value={target} onChange={(id) => { setTarget(id); setRes(null); }} /></div>
          <div><label className="label">Kind of change</label>
            <Segmented value={change} onChange={setChange} options={[{ value: 'modify', label: 'Modify behaviour' }, { value: 'signature', label: 'Change a method' }, { value: 'remove', label: 'Remove' }]} /></div>
          <button className="btn btn-primary btn-lg" style={{ height: 40 }} disabled={!target || busy || (change === 'signature' && !method)} onClick={() => run()}>
            {busy ? <Spinner /> : <Icon name="impact" size={16} />}Predict impact
          </button>
        </div>
        {change === 'signature' && unit && (
          <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>
            <span className="small muted">Method:</span>
            {unit.methods.filter((m) => !m.constructor && m.public !== false).map((m) => (
              <span key={m.name + m.line} className={`chip ${method === m.name ? 'active' : ''}`} onClick={() => setMethod(m.name)}>{m.name}()</span>
            ))}
          </div>
        )}
        {err && <div className="callout danger" style={{ marginTop: 12 }}>{err}</div>}
      </div>

      {!res && !busy && <div className="card"><Empty icon="impact" title="Pick a component and predict the blast radius">Try a high-risk service such as {twin.summary.high_risk.slice(0, 2).map((h) => twin.units[h]?.name).join(' or ') || 'a service'}.</Empty></div>}

      {res && (
        <div ref={out}>
          <div className="grid g3" style={{ marginBottom: 18 }}>
            <div className={`risk-hero ${res.risk.level}`}>
              <div className="eyebrow" style={{ color: 'rgba(255,255,255,.8)' }}>Potential impact</div>
              <div className="row" style={{ alignItems: 'flex-end', gap: 12, marginTop: 6, flexWrap: 'wrap' }}>
                <div style={{ fontSize: 'clamp(34px, 4vw, 54px)', fontWeight: 800, letterSpacing: '-0.04em', lineHeight: 1 }}>{res.risk.level}</div>
                <div style={{ paddingBottom: 6, opacity: 0.9 }}><span className="risk-score num" style={{ fontSize: 22, fontWeight: 700 }}>{res.risk.score}</span>/100</div>
              </div>
              <div style={{ marginTop: 12, fontSize: 14.5, opacity: 0.95 }}>{res.summary}</div>
              <div className="col" style={{ gap: 4, marginTop: 14 }}>
                {res.risk.reasons.map((r: string) => <div key={r} className="small" style={{ opacity: 0.92 }}>• {r}</div>)}
              </div>
            </div>
            <div className="card span2 pad-0" style={{ minHeight: 330 }}>
              <div style={{ position: 'absolute', top: 14, left: 18, zIndex: 3 }}>
                <div className="h3">Blast radius</div>
                <div className="card-sub">Rings = distance from {res.target.name} · red = changed</div>
              </div>
              <div style={{ position: 'absolute', inset: '58px 0 0 0' }}>
                {sub && <GraphView nodes={sub.nodes} edges={sub.edges} layout="concentric" concentricKey={sub.dist} highlight={sub.dist}
                  onSelect={(id) => { if (id && twin.units[id]) openCode(twin.units[id].file, twin.units[id].line); }} />}
              </div>
            </div>
          </div>

          {res.chains.length > 0 && (
            <div className="card" style={{ marginBottom: 18 }} data-reveal>
              <SectionTitle icon="link" title="How the change propagates" sub="Shortest dependency paths from the changed component to its consumers" />
              <div className="col" style={{ gap: 10 }}>
                {res.chains.map((ch: any[], i: number) => (
                  <div key={i} className="chain">
                    {ch.map((n, k) => (
                      <span key={k} className="row" style={{ gap: 6 }}>
                        <span className={`node ${k === 0 ? 'target' : ''}`} style={k ? { borderColor: LAYER_COLORS[n.layer], color: 'var(--text)' } : undefined}>{n.name}</span>
                        {k < ch.length - 1 && <Icon name="arrow" size={14} className="arr" />}
                      </span>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid g3" style={{ marginBottom: 18 }}>
            <div className="card span2" data-reveal>
              <SectionTitle icon="layers" title={`Potentially affected · ${res.stats.affected}`} sub="Grouped by how directly they depend on the change" />
              {groups.length === 0 && <div className="muted small">Nothing depends on this component.</div>}
              {groups.map(([k, rows]) => (
                <div key={k} style={{ marginBottom: 14 }}>
                  <div className="eyebrow" style={{ marginBottom: 6 }}>{k} · {rows.length}</div>
                  <table className="table">
                    <tbody>
                      {rows.map((a: any) => (
                        <tr key={a.id} className="click" onClick={() => openCode(a.file, a.line)}>
                          <td style={{ width: '32%' }}><b>{a.name}</b></td>
                          <td><LayerTag layer={a.layer} small /></td>
                          <td className="small muted">{a.module ? modName(a.module) : ''}</td>
                          <td className="small muted">{a.via}</td>
                          <td style={{ textAlign: 'right' }}><span className={`dot ${a.risk}`} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
            <div className="col" style={{ gap: 18 }}>
              <div className="card" data-reveal>
                <SectionTitle icon="api" title={`API endpoints · ${res.endpoints.length}`} />
                {res.endpoints.map((e: any) => <div key={e.id} className="mono small" style={{ padding: '4px 0' }}>{e.name}</div>)}
                {!res.endpoints.length && <div className="small muted">No public API on the propagation path.</div>}
              </div>
              <div className="card" data-reveal>
                <SectionTitle icon="db" title="Data touched" />
                {res.data.map((d: any) => <div key={d.id} className="small" style={{ padding: '4px 0' }}><b>{d.name}</b> <span className="subtle">via {d.path.slice(1, -1).map((p: string) => twin.units[p]?.name || p).join(' → ')}</span></div>)}
                {!res.data.length && <div className="small muted">No database access.</div>}
              </div>
              <div className="card" data-reveal>
                <SectionTitle icon="check" title={`Tests to run · ${res.tests.length}`} />
                {res.tests.map((t: any) => <div key={t.id} className="small" style={{ padding: '3px 0' }}>{t.name}</div>)}
                {!res.tests.length && <div className="callout warn small">No tests cover this area — add some before changing it.</div>}
              </div>
            </div>
          </div>
          <div className="card" data-reveal>
            <SectionTitle icon="sparkle" title="AI explanation" sub="Why this risk level, and what to do before merging" />
            <AIExplain pid={pid} kind="impact" payload={{ target: res.target, change: res.change, method: res.method, risk: res.risk, summary: res.summary, stats: res.stats,
              direct: res.affected.filter((a: any) => a.distance === 1).map((a: any) => `${a.name} (${a.via})`), endpoints: res.endpoints.map((e: any) => e.name),
              frontend: res.frontend.map((f: any) => f.name), data: res.data.map((d: any) => d.name), tests: res.tests.map((t: any) => t.name),
              chains: res.chains.map((c: any[]) => c.map((x) => x.name).join(' → ')) }} />
          </div>
        </div>
      )}
      <div className="footer-note">Impact = reverse reachability on the dependency graph (incl. interface polymorphism and HTTP links), weighted by distance, centrality, tests and risk.</div>
    </div>
  );
}
