import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../lib/api';
import { useReveal } from '../lib/anim';
import { useProject, useTwin } from '../lib/store';
import { LAYER_COLORS, short } from '../lib/ui';
import Icon from '../components/Icon';
import { Empty, SectionTitle, Spinner } from '../components/Common';
import { LineChart, Sparkbars } from '../components/Charts';
import GraphView, { GEdge, GNode } from '../components/GraphView';

export default function Evolution() {
  const twin = useTwin();
  const { meta, openCode } = useProject();
  const pid = meta!.id;
  const h = twin.history || {};
  const ref = useRef<HTMLDivElement>(null);
  const [evo, setEvo] = useState<any>(null);
  const [snap, setSnap] = useState(0);
  useReveal(ref, [!!evo]);

  useEffect(() => {
    let t: any;
    const poll = async () => {
      const e = await api.evolution(pid);
      setEvo(e);
      if (e.status === 'running') t = setTimeout(poll, 1200);
      else if (e.snapshots?.length) setSnap(e.snapshots.length - 1);
    };
    poll();
    return () => clearTimeout(t);
  }, [pid]);
  const start = async () => { setEvo(await api.runEvolution(pid)); setTimeout(async function p() { const e = await api.evolution(pid); setEvo(e); if (e.status === 'running') setTimeout(p, 1200); else setSnap((e.snapshots?.length || 1) - 1); }, 1000); };

  const snapGraph = useMemo(() => {
    const s = evo?.snapshots?.[snap];
    if (!s) return null;
    const nodes: GNode[] = s.modules.map((m: any) => ({ id: m.id, label: `${m.name}`, color: m.app.includes('front') ? LAYER_COLORS.page : LAYER_COLORS.service, size: 18 + Math.min(36, Math.sqrt(m.loc) * 1.5) }));
    const ids = new Set(nodes.map((n) => n.id));
    const edges: GEdge[] = s.module_edges.filter((e: any) => ids.has(e.source) && ids.has(e.target)).map((e: any) => ({ id: e.source + e.target, source: e.source, target: e.target, weight: Math.min(6, e.weight) }));
    return { nodes, edges };
  }, [evo, snap]);

  if (!h.available) {
    return <div className="page"><div className="page-header"><div><div className="eyebrow">Git history</div><h1 className="h1">Evolution</h1></div></div>
      <div className="card"><Empty icon="history" title="No git history in this project">Import from GitHub or include the .git folder in your ZIP to unlock churn, hotspots and architecture evolution.</Empty></div></div>;
  }
  const snaps = evo?.snapshots || [];
  return (
    <div className="page" ref={ref}>
      <div className="page-header">
        <div><div className="eyebrow">How the project changed over time</div><h1 className="h1">Project Evolution</h1>
          <div className="muted" style={{ marginTop: 6 }}>{h.commits} commits by {h.authors.length} authors · {h.first_commit?.slice(0, 10)} → {h.last_commit?.slice(0, 10)} · {h.fix_commits} bug-fix commits</div></div>
      </div>
      <div className="grid g3" style={{ marginBottom: 18 }}>
        <div className="card span2" data-reveal>
          <SectionTitle icon="clock" title="Commit activity" sub="Commits per week" />
          <Sparkbars data={h.timeline.map((t: any) => t.commits)} labels={h.timeline.map((t: any) => t.week)} height={150} color="var(--blue)" />
          <div className="row between tiny subtle" style={{ marginTop: 6 }}><span>{h.timeline[0]?.week}</span><span>{h.timeline[h.timeline.length - 1]?.week}</span></div>
        </div>
        <div className="card" data-reveal>
          <SectionTitle icon="user" title="Contributors" />
          {h.authors.map((a: any) => (
            <div key={a.name} className="row between small" style={{ padding: '6px 0' }}>
              <div className="row"><div className="avatar" style={{ width: 26, height: 26, borderRadius: 13, fontSize: 11, fontWeight: 700 }}>{a.name.split(' ').map((x: string) => x[0]).join('').slice(0, 2)}</div>{a.name}</div>
              <b className="num">{a.commits}</b>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 18 }} data-reveal>
        <SectionTitle icon="twin" title="Architecture evolution" sub="The twin rebuilt at evenly-spaced commits"
          right={evo?.status !== 'running' && <button className="btn btn-primary btn-sm" onClick={start}><Icon name="refresh" size={14} />{snaps.length ? 'Recompute' : 'Analyse evolution'}</button>} />
        {evo?.status === 'running' && <div className="row small muted" style={{ marginBottom: 12 }}><Spinner size={13} />Rebuilding historic twins… {Math.round((evo.progress || 0) * 100)}%</div>}
        {!snaps.length && evo?.status !== 'running' && <Empty icon="history" title="See how the architecture grew">CodeTwin checks out historic commits and rebuilds a lightweight twin for each.</Empty>}
        {snaps.length > 0 && (
          <>
            <div className="row wrap" style={{ gap: 6, marginBottom: 14 }}>
              {snaps.map((s: any, i: number) => (
                <span key={s.sha} className={`chip ${i === snap ? 'active' : ''}`} onClick={() => setSnap(i)}>v{i + 1} · {s.date.slice(0, 10)}</span>
              ))}
            </div>
            <div className="grid g3">
              <div className="card flat pad-0 span2" style={{ height: 380, background: 'var(--bg-2)' }}>
                {snapGraph && <div style={{ position: 'absolute', inset: 0 }}><GraphView key={snap} nodes={snapGraph.nodes} edges={snapGraph.edges} /></div>}
              </div>
              <div>
                <div className="eyebrow">Snapshot v{snap + 1}</div>
                <div className="h3" style={{ margin: '4px 0 2px' }}>{snaps[snap].message}</div>
                <div className="tiny subtle mono">{snaps[snap].sha.slice(0, 8)} · {snaps[snap].date.slice(0, 10)}</div>
                <div className="tiny muted" style={{ marginTop: 6 }}>{snaps[snap].architecture}</div>
                <dl className="kv" style={{ marginTop: 14 }}>
                  <dt>Components</dt><dd>{snaps[snap].counts.units}</dd><dt>Modules</dt><dd>{snaps[snap].counts.modules}</dd>
                  <dt>Lines of code</dt><dd>{snaps[snap].counts.loc}</dd><dt>Endpoints</dt><dd>{snaps[snap].counts.endpoints}</dd>
                  <dt>Tables</dt><dd>{snaps[snap].tables}</dd><dt>Health</dt><dd>{snaps[snap].health}</dd>
                </dl>
              </div>
            </div>
            <div style={{ marginTop: 18 }}>
              <LineChart labels={snaps.map((_: any, i: number) => `v${i + 1}`)} series={[
                { name: 'Components', color: '#0a84ff', values: snaps.map((s: any) => s.counts.units) },
                { name: 'Dependencies', color: '#bf5af2', values: snaps.map((s: any) => s.counts.dependencies) },
                { name: 'Health', color: '#30d158', values: snaps.map((s: any) => s.health) },
              ]} />
              <div className="row small muted" style={{ gap: 14, justifyContent: 'center' }}>
                <span className="row" style={{ gap: 5 }}><span className="dot" style={{ background: '#0a84ff' }} />Components</span>
                <span className="row" style={{ gap: 5 }}><span className="dot" style={{ background: '#bf5af2' }} />Dependencies</span>
                <span className="row" style={{ gap: 5 }}><span className="dot" style={{ background: '#30d158' }} />Health</span>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="grid g2">
        <div className="card" data-reveal>
          <SectionTitle icon="bolt" title="Most changed files" sub="With complexity — the classic hotspot signal" />
          <table className="table"><thead><tr><th>File</th><th>Commits</th><th>Fixes</th><th>CC</th><th>Authors</th></tr></thead>
            <tbody>{(h.hotspots || []).slice(0, 10).map((r: any) => (
              <tr key={r.path} className="click" onClick={() => openCode(r.path)}><td><b>{short(r.path)}</b></td><td className="num">{r.churn}</td><td className="num">{r.fixes}</td><td className="num">{r.complexity}</td><td className="num">{r.authors}</td></tr>
            ))}</tbody></table>
          {(h.hotspots || [])[0] && <div className="callout danger small" style={{ marginTop: 12 }}><Icon name="alert" size={15} />
            <span><b>{short(h.hotspots[0].path)}</b> is the top hotspot: changed {h.hotspots[0].churn} times ({h.hotspots[0].fixes} fixes) with complexity {h.hotspots[0].complexity}.</span></div>}
        </div>
        <div className="card" data-reveal>
          <SectionTitle icon="history" title="Recent commits" />
          {h.recent.slice(0, 12).map((c: any) => (
            <div key={c.sha} className="row small" style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
              <span className="mono tiny subtle">{c.sha.slice(0, 7)}</span>
              <span className="grow ellipsis">{c.message}</span>
              {c.fix && <span className="badge high">fix</span>}
              <span className="tiny subtle nowrap">{c.date.slice(0, 10)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
