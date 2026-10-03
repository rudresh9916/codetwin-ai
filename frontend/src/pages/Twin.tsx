import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../lib/api';
import { gsap } from '../lib/anim';
import { nodeLayer, nodeName, useProject, useTwin } from '../lib/store';
import { useRouter } from '../lib/router';
import { LAYER_COLORS, LAYER_LABEL, modName, RISK_COLORS } from '../lib/ui';
import Icon from '../components/Icon';
import { LayerTag, RiskBadge, Segmented, Spinner } from '../components/Common';
import GraphView, { GEdge, GNode, GraphHandle } from '../components/GraphView';

const PALETTE = ['#0a84ff', '#bf5af2', '#ff9f0a', '#30d158', '#ff375f', '#5e5ce6', '#40c8e0', '#ffd60a', '#ac8e68', '#64d2ff', '#ff6b6b', '#66d4cf'];

export default function TwinPage() {
  const twin = useTwin();
  const { meta, openCode, index } = useProject();
  const { loc, navigate } = useRouter();
  const pid = meta!.id;
  const [view, setView] = useState<'components' | 'modules'>('components');
  const [colorBy, setColorBy] = useState<'layer' | 'risk' | 'module'>('layer');
  const [showEp, setShowEp] = useState(false);
  const [showDb, setShowDb] = useState(true);
  const [showTests, setShowTests] = useState(false);
  const [group, setGroup] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(new Set(['dto', 'exception', 'types']));
  const [selected, setSelected] = useState<string | null>(loc.query.get('node'));
  const [impact, setImpact] = useState<any>(null);
  const [impLoading, setImpLoading] = useState(false);
  const [q, setQ] = useState('');
  const graph = useRef<GraphHandle>(null);
  const insp = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const m = loc.query.get('module');
    if (m) { setView('modules'); setSelected(m); }
    const n = loc.query.get('node');
    if (n) { setSelected(n); setTimeout(() => graph.current?.focus(n), 1300); }
  }, []);
  useEffect(() => { if (insp.current) gsap.fromTo(insp.current, { x: 30, opacity: 0 }, { x: 0, opacity: 1, duration: 0.4, ease: 'power3.out' }); }, [selected]);

  const modColor = useMemo(() => {
    const m: Record<string, string> = {};
    twin.modules.forEach((mod, i) => { m[mod.id] = PALETTE[i % PALETTE.length]; });
    return m;
  }, [twin]);

  const { nodes, edges } = useMemo(() => {
    const nodes: GNode[] = [];
    const edges: GEdge[] = [];
    if (view === 'modules') {
      for (const m of twin.modules) {
        const lay = Object.entries(m.layers).sort((a, b) => b[1] - a[1])[0]?.[0] || 'module';
        nodes.push({ id: m.id, label: `${m.name}`, color: colorBy === 'module' ? modColor[m.id] : colorBy === 'risk' ? RISK_COLORS[m.risk >= 0.66 ? 'high' : m.risk >= 0.45 ? 'medium' : 'low'] : LAYER_COLORS[lay] || '#8e8e93',
          size: 22 + Math.min(46, Math.sqrt(m.loc) * 1.7) });
      }
      const agg: Record<string, number> = {};
      for (const e of twin.edges) {
        const su = twin.units[e.source];
        const tu = twin.units[e.target] || (twin.endpoints[e.target] && twin.units[twin.endpoints[e.target].unit]);
        if (!su || !tu || su.is_test || su.module === tu.module) continue;
        const k = `${su.module}|${tu.module}|${e.types.includes('http') ? 'http' : 'dep'}`;
        agg[k] = (agg[k] || 0) + 1;
      }
      Object.entries(agg).forEach(([k, w]) => { const [s, t, ty] = k.split('|'); edges.push({ id: k, source: s, target: t, type: ty, weight: w, label: String(w) }); });
      return { nodes, edges };
    }
    const visible = new Set<string>();
    for (const u of Object.values(twin.units)) {
      if (u.is_test && !showTests) continue;
      if (hidden.has(u.layer)) continue;
      visible.add(u.id);
      const color = colorBy === 'risk' ? RISK_COLORS[u.risk.level] : colorBy === 'module' ? modColor[u.module] : LAYER_COLORS[u.layer] || '#8e8e93';
      nodes.push({ id: u.id, label: u.name, color, size: 20 + Math.min(34, Math.sqrt(u.metrics.logic + u.metrics.fan_in * 3) * 4.2),
        parent: group ? `mod:${u.module}` : undefined, kind: u.kind === 'interface' ? 'interface' : '' });
    }
    if (showEp && !hidden.has('endpoint')) for (const e of Object.values(twin.endpoints)) {
      visible.add(e.id);
      nodes.push({ id: e.id, label: `${e.method} ${e.path}`, color: LAYER_COLORS.endpoint, size: 16, kind: 'endpoint', parent: group && twin.units[e.unit] ? `mod:${twin.units[e.unit].module}` : undefined });
    }
    if (showDb && !hidden.has('table')) for (const t of Object.values(twin.tables)) {
      visible.add(t.id);
      nodes.push({ id: t.id, label: t.name, color: LAYER_COLORS.table, size: 28, kind: 'table' });
    }
    if (group) {
      const used = new Set(nodes.map((n) => n.parent).filter(Boolean));
      for (const m of twin.modules) if (used.has(`mod:${m.id}`)) nodes.push({ id: `mod:${m.id}`, label: `${m.name}${m.app && m.app !== m.name ? ' · ' + m.app : ''}`, color: modColor[m.id], isParent: true });
    }
    for (const e of twin.edges) {
      let s = e.source, t = e.target;
      if (!showEp) {
        // collapse frontend -> endpoint -> controller into a direct HTTP edge
        if (twin.endpoints[t]) t = twin.endpoints[t].unit;
        if (twin.endpoints[s]) continue;
      }
      if (!visible.has(s) || !visible.has(t) || s === t) continue;
      edges.push({ id: `${s}>${t}>${e.type}`, source: s, target: t, type: e.types.includes('http') ? 'http' : e.type, weight: e.weight });
    }
    const uniq: Record<string, GEdge> = {};
    edges.forEach((e) => { uniq[e.id] = e; });
    return { nodes, edges: Object.values(uniq) };
  }, [twin, view, colorBy, showEp, showDb, showTests, group, hidden, modColor]);

  const highlight = useMemo(() => {
    if (!impact) return null;
    const h: Record<string, number> = { [impact.target.id]: 0 };
    for (const a of [...impact.affected, ...impact.endpoints, ...impact.tests]) h[a.id] = a.distance;
    for (const d of impact.data) h[d.id] = 1;
    return h;
  }, [impact]);

  const runImpact = async (id: string) => {
    setImpLoading(true);
    try { setImpact(await api.impact(pid, { target: id, change: 'modify' })); setSelected(null); } finally { setImpLoading(false); }
  };

  const sel = selected ? (twin.units[selected] || null) : null;
  const selModule = selected && view === 'modules' ? twin.modules.find((m) => m.id === selected) : null;
  const layersPresent = useMemo(() => {
    const s = new Set<string>(Object.values(twin.units).map((u) => u.layer));
    if (showEp) s.add('endpoint');
    if (showDb && Object.keys(twin.tables).length) s.add('table');
    return [...s].filter((l) => l !== 'test');
  }, [twin, showEp, showDb]);

  return (
    <div className="page" style={{ maxWidth: 'none', paddingBottom: 20 }}>
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <div className="eyebrow">Interactive architecture graph</div>
          <h1 className="h1">Digital Twin</h1>
        </div>
        <div className="row wrap">
          <Segmented value={view} onChange={(v) => { setView(v); setSelected(null); setImpact(null); }} options={[{ value: 'components', label: 'Components' }, { value: 'modules', label: 'Modules' }]} />
          <Segmented value={colorBy} onChange={setColorBy} options={[{ value: 'layer', label: 'Layer' }, { value: 'risk', label: 'Risk' }, { value: 'module', label: 'Module' }]} />
        </div>
      </div>

      <div className="graph-wrap">
        <GraphView ref={graph} nodes={nodes} edges={edges} selected={selected} onSelect={setSelected} highlight={highlight} />

        <div className="graph-toolbar">
          <div className="floating row" style={{ padding: 6, gap: 6 }}>
            <Icon name="search" size={15} style={{ marginLeft: 6, color: 'var(--text-3)' }} />
            <input className="input" style={{ height: 30, border: 0, width: 200, background: 'transparent', boxShadow: 'none' }} placeholder="Find & focus…" value={q}
              onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => {
                if (e.key !== 'Enter') return;
                const hit = nodes.find((n) => !n.isParent && n.label.toLowerCase().includes(q.toLowerCase()));
                if (hit) { setSelected(hit.id); graph.current?.focus(hit.id); }
              }} />
          </div>
          {view === 'components' && (
            <div className="floating row wrap" style={{ padding: 6, gap: 4 }}>
              <span className={`chip ${group ? 'active' : ''}`} onClick={() => setGroup(!group)}><Icon name="layers" size={13} />Group by module</span>
              <span className={`chip ${showEp ? 'active' : ''}`} onClick={() => setShowEp(!showEp)}><Icon name="api" size={13} />Endpoints</span>
              <span className={`chip ${showDb ? 'active' : ''}`} onClick={() => setShowDb(!showDb)}><Icon name="db" size={13} />Tables</span>
              <span className={`chip ${showTests ? 'active' : ''}`} onClick={() => setShowTests(!showTests)}><Icon name="check" size={13} />Tests</span>
            </div>
          )}
          {impact && (
            <div className="floating row" style={{ padding: '8px 12px', gap: 10, borderColor: 'var(--red)' }}>
              <span className={`badge ${impact.risk.level.toLowerCase()}`}>{impact.risk.level}</span>
              <span className="small"><b>{impact.target.name}</b> → {impact.stats.affected} components, {impact.stats.endpoints} endpoints</span>
              <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/p/${pid}/impact?target=${encodeURIComponent(impact.target.id)}`)}>Details</button>
              <button className="btn btn-secondary btn-sm btn-icon" onClick={() => setImpact(null)}><Icon name="x" size={14} /></button>
            </div>
          )}
        </div>

        {view === 'components' && (
          <div className="legend floating">
            {layersPresent.map((l) => (
              <span key={l} className={hidden.has(l) ? 'off' : ''} onClick={() => { const h = new Set(hidden); h.has(l) ? h.delete(l) : h.add(l); setHidden(h); }}>
                <span className="dot" style={{ background: LAYER_COLORS[l] }} />{LAYER_LABEL[l] || l}
              </span>
            ))}
          </div>
        )}
        <div className="zoom-ctl floating">
          <button onClick={() => graph.current?.zoom(1.25)} title="Zoom in">+</button>
          <button onClick={() => graph.current?.zoom(0.8)} title="Zoom out">−</button>
          <button onClick={() => graph.current?.fit()} title="Fit"><Icon name="fit" size={15} /></button>
          <button title="Export PNG" onClick={() => { const d = graph.current?.png(); if (d) { const a = document.createElement('a'); a.href = d; a.download = `${twin.name}-twin.png`; a.click(); } }}><Icon name="download" size={15} /></button>
        </div>

        {sel && (
          <div className="inspector floating" ref={insp}>
            <div className="row between" style={{ alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <LayerTag layer={sel.layer} />
                <div className="h2" style={{ marginTop: 4, wordBreak: 'break-word' }}>{sel.name}</div>
                <div className="tiny subtle" style={{ wordBreak: 'break-all' }}>{sel.file}</div>
              </div>
              <button className="btn btn-secondary btn-icon btn-sm" onClick={() => setSelected(null)}><Icon name="x" size={14} /></button>
            </div>
            <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>
              <RiskBadge level={sel.risk.level} label={`Risk ${sel.risk.level}`} />
              <span className="badge neutral">{modName(sel.module)}</span>
              {sel.god_class && <span className="badge high">God class</span>}
              {sel.metrics.tested ? <span className="badge low">Tested</span> : <span className="badge medium">No tests</span>}
            </div>
            <dl className="kv" style={{ marginTop: 16 }}>
              <dt>Type</dt><dd style={{ textTransform: 'capitalize' }}>{sel.kind} · {sel.language}</dd>
              <dt>Methods</dt><dd>{sel.metrics.methods}</dd>
              <dt>Complexity (WMC)</dt><dd>{sel.metrics.wmc} · max {sel.metrics.max_cc}</dd>
              <dt>Dependencies</dt><dd>{sel.metrics.fan_out}</dd>
              <dt>Dependents</dt><dd>{sel.metrics.fan_in} direct · {sel.metrics.dependents_transitive} total</dd>
              <dt>Instability</dt><dd>{sel.metrics.instability}</dd>
              <dt>Lines</dt><dd>{sel.loc}</dd>
              {sel.metrics.churn > 0 && <><dt>Changes</dt><dd>{sel.metrics.churn} commits · {sel.metrics.fixes} fixes</dd></>}
            </dl>
            {sel.risk.reasons.length > 0 && (
              <div className="callout warn" style={{ marginTop: 14, flexDirection: 'column', gap: 4 }}>
                {sel.risk.reasons.map((r) => <div key={r} className="small">• {r}</div>)}
              </div>
            )}
            <div className="row wrap" style={{ marginTop: 14, gap: 6 }}>
              <button className="btn btn-primary btn-sm" onClick={() => runImpact(sel.id)} disabled={impLoading}>{impLoading ? <Spinner size={12} /> : <Icon name="impact" size={14} />}What breaks if I change it?</button>
              <button className="btn btn-secondary btn-sm" onClick={() => openCode(sel.file, sel.line, sel.endLine)}><Icon name="code" size={14} />Code</button>
              <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/p/${pid}/ask?q=${encodeURIComponent(`What does ${sel.name} do?`)}`)}><Icon name="chat" size={14} />Ask</button>
            </div>
            <NeighborList title="Depends on" ids={[...new Set(index.dependencies[sel.id] || [])]} onPick={(id) => { setSelected(id); graph.current?.focus(id); }} />
            <NeighborList title="Used by" ids={[...new Set(index.dependents[sel.id] || [])]} onPick={(id) => { setSelected(id); graph.current?.focus(id); }} />
            {sel.methods.length > 0 && (
              <>
                <div className="eyebrow" style={{ margin: '16px 0 6px' }}>Methods</div>
                {sel.methods.filter((m) => !m.constructor).slice(0, 14).map((m) => (
                  <div key={m.name + m.line} className="row between small clickable" style={{ padding: '4px 0' }} onClick={() => openCode(sel.file, m.line, m.endLine)}>
                    <span className="mono ellipsis">{m.name}()</span>
                    <span className={`badge ${m.complexity > 10 ? 'high' : m.complexity > 5 ? 'medium' : 'neutral'}`}>CC {m.complexity}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
        {!sel && selected && twin.endpoints[selected] && (
          <div className="inspector floating" ref={insp}>
            <LayerTag layer="endpoint" />
            <div className="h2 mono" style={{ fontSize: 18, marginTop: 6 }}>{twin.endpoints[selected].method} {twin.endpoints[selected].path}</div>
            <div className="small muted" style={{ marginTop: 6 }}>Handled by {twin.units[twin.endpoints[selected].unit]?.name}.{twin.endpoints[selected].handler}()</div>
            <NeighborList title="Called by" ids={twin.endpoints[selected].consumers} onPick={setSelected} />
            <button className="btn btn-primary btn-sm" style={{ marginTop: 14 }} onClick={() => runImpact(selected)}><Icon name="impact" size={14} />Impact</button>
          </div>
        )}
        {selModule && (
          <div className="inspector floating" ref={insp}>
            <div className="eyebrow">Module</div>
            <div className="h2" style={{ marginTop: 4 }}>{selModule.name}</div>
            <div className="small muted">{selModule.app || 'root'} · {selModule.loc} LOC · {selModule.files} files</div>
            <dl className="kv" style={{ marginTop: 14 }}>
              <dt>Afferent coupling (Ca)</dt><dd>{selModule.metrics.ca}</dd>
              <dt>Efferent coupling (Ce)</dt><dd>{selModule.metrics.ce}</dd>
              <dt>Instability (I)</dt><dd>{selModule.metrics.instability}</dd>
              <dt>Abstractness (A)</dt><dd>{selModule.metrics.abstractness}</dd>
              <dt>Distance from main seq.</dt><dd>{selModule.metrics.distance}</dd>
            </dl>
            <div className="eyebrow" style={{ margin: '16px 0 6px' }}>Components</div>
            {selModule.units.map((id) => (
              <div key={id} className="row between small clickable" style={{ padding: '4px 0' }} onClick={() => { setView('components'); setSelected(id); setTimeout(() => graph.current?.focus(id), 1200); }}>
                <span>{twin.units[id].name}</span><LayerTag layer={twin.units[id].layer} small />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  function NeighborList({ title, ids, onPick }: { title: string; ids: string[]; onPick: (id: string) => void }) {
    if (!ids.length) return null;
    return (
      <>
        <div className="eyebrow" style={{ margin: '16px 0 6px' }}>{title} · {ids.length}</div>
        <div className="row wrap" style={{ gap: 5 }}>
          {ids.slice(0, 24).map((id) => (
            <span key={id} className="chip" style={{ height: 26, fontSize: 12 }} onClick={() => onPick(id)}>
              <span className="dot" style={{ background: LAYER_COLORS[nodeLayer(twin, id)] || '#8e8e93' }} />{nodeName(twin, id)}
            </span>
          ))}
        </div>
      </>
    );
  }
}
