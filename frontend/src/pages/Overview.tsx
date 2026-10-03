import { useMemo, useRef } from 'react';
import { api } from '../lib/api';
import { useReveal } from '../lib/anim';
import { useProject, useTwin } from '../lib/store';
import { useRouter } from '../lib/router';
import { DIM_LABEL, LAYER_COLORS, LAYER_LABEL, modName, RISK_COLORS, scoreColor } from '../lib/ui';
import Icon from '../components/Icon';
import { LayerTag, RiskBadge, SectionTitle, StatCard } from '../components/Common';
import { Bar, ScoreRing } from '../components/Charts';
import GraphView, { GEdge, GNode } from '../components/GraphView';

export const SUGGESTED = [
  'Explain this project.',
  'Which module is most critical?',
  'Where is authentication implemented?',
  'Which APIs are unused?',
  'What could be affected if I modify UserService?',
  'How does the checkout process work?',
];

export default function Overview() {
  const twin = useTwin();
  const { meta, reload, openCode } = useProject();
  const { navigate } = useRouter();
  const ref = useRef<HTMLDivElement>(null);
  useReveal(ref, [twin.generated_at]);
  const pid = meta!.id;
  const s = twin.summary;
  const c = s.counts;

  const moduleGraph = useMemo(() => {
    const nodes: GNode[] = twin.modules.map((m) => {
      const lay = Object.entries(m.layers).sort((a, b) => b[1] - a[1])[0]?.[0] || 'module';
      return { id: m.id, label: m.name, color: LAYER_COLORS[lay] || '#8e8e93', size: 26 + Math.min(44, Math.sqrt(m.loc) * 1.8) };
    });
    const seen = new Set<string>();
    const edges: GEdge[] = [];
    for (const e of twin.edges) {
      const su = twin.units[e.source];
      const tu = twin.units[e.target] || (twin.endpoints[e.target] && twin.units[twin.endpoints[e.target].unit]);
      if (!su || !tu || su.is_test || su.module === tu.module) continue;
      const k = su.module + '>' + tu.module;
      if (seen.has(k)) continue;
      seen.add(k);
      edges.push({ id: k, source: su.module, target: tu.module, type: e.types.includes('http') ? 'http' : 'dep' });
    }
    const linked = new Set(edges.flatMap((e) => [e.source, e.target]));
    return { nodes: nodes.filter((n) => linked.has(n.id)), edges };
  }, [twin]);

  const sortedDims = Object.entries(twin.health.dimensions).sort((a, b) => a[1].score - b[1].score);
  const topIssues = twin.issues.filter((i) => i.severity === 'critical' || i.severity === 'high').slice(0, 6);
  const layers = Object.entries(s.layers).sort((a, b) => b[1] - a[1]);
  const totalLayer = layers.reduce((a, [, v]) => a + v, 0) || 1;

  return (
    <div className="page" ref={ref}>
      <div className="page-header">
        <div>
          <div className="eyebrow row" style={{ gap: 6 }}><span className="dot low" /> Digital Twin · analysed in {twin.duration_s}s</div>
          <h1 className="h1">{twin.name}</h1>
          <div className="muted" style={{ marginTop: 6, fontSize: 15 }}>{s.architecture}</div>
          <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>
            {Object.entries(s.languages).filter(([l]) => ['Java', 'TypeScript', 'JavaScript', 'SQL', 'Kotlin', 'Python'].includes(l)).map(([l, n]) => <span key={l} className="badge blue">{l} · {n}</span>)}
            {s.frameworks.slice(0, 8).map((f) => <span key={f.name} className="badge neutral">{f.name}</span>)}
            {s.databases.map((d) => <span key={d} className="badge purple"><Icon name="db" size={11} />{d}</span>)}
          </div>
        </div>
        <div className="row">
          <a className="btn btn-outline btn-sm" href={api.reportUrl(pid)}><Icon name="download" size={14} />Twin JSON</a>
          <button className="btn btn-outline btn-sm" onClick={async () => { await api.reanalyze(pid); reload(); }}><Icon name="refresh" size={14} />Re-analyse</button>
          <button className="btn btn-primary btn-sm" onClick={() => navigate(`/p/${pid}/twin`)}><Icon name="twin" size={14} />Open Digital Twin</button>
        </div>
      </div>

      {twin.warnings.length > 0 && <div className="callout warn" style={{ marginBottom: 16 }}><Icon name="alert" size={16} />{twin.warnings.join(' · ')}</div>}

      <div className="grid g6" style={{ marginBottom: 18 }}>
        <StatCard label="Source files" value={c.files} icon="file" color="#0a84ff" sub={`${c.loc.toLocaleString()} lines of code`} onClick={() => navigate(`/p/${pid}/code`)} />
        <StatCard label="Classes & components" value={c.units} icon="cube" color="#bf5af2" sub={`${c.functions} functions`} onClick={() => navigate(`/p/${pid}/twin`)} />
        <StatCard label="Modules" value={c.modules} icon="layers" color="#5e5ce6" sub={`${twin.apps.length} app${twin.apps.length === 1 ? '' : 's'}`} />
        <StatCard label="Dependencies" value={c.dependencies} icon="link" color="#ff9f0a" sub={`${twin.cycles.length} cycle${twin.cycles.length === 1 ? '' : 's'}`} />
        <StatCard label="API endpoints" value={c.endpoints} icon="api" color="#ff375f" sub={`${s.unused_endpoints.length} unused`} />
        <StatCard label="Database tables" value={c.tables} icon="db" color="#30d158" sub={s.databases.join(', ') || '—'} />
      </div>

      <div className="grid g3" style={{ marginBottom: 18 }}>
        <div className="card clickable" data-reveal onClick={() => navigate(`/p/${pid}/health`)}>
          <SectionTitle icon="health" title="Architecture Health" sub="Derived from measurable metrics" right={<span className="badge neutral">Grade {twin.health.grade}</span>} />
          <div className="row" style={{ gap: 22, alignItems: 'center' }}>
            <ScoreRing value={twin.health.overall} size={138} label="of 100" />
            <div className="col grow" style={{ gap: 9 }}>
              {sortedDims.slice(0, 5).map(([k, d]) => (
                <div key={k}>
                  <div className="row between small"><span>{DIM_LABEL[k]}</span><b className="num" style={{ color: scoreColor(d.score) }}>{d.score}</b></div>
                  <Bar value={d.score} />
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="card pad-0 span2" data-reveal style={{ minHeight: 300 }}>
          <div style={{ position: 'absolute', top: 16, left: 20, zIndex: 3 }}>
            <div className="h3 row" style={{ gap: 8 }}><Icon name="twin" size={17} style={{ color: 'var(--text-2)' }} />Architecture map</div>
            <div className="card-sub">Modules and their dependencies · dashed = HTTP</div>
          </div>
          <button className="btn btn-secondary btn-sm" style={{ position: 'absolute', top: 14, right: 14, zIndex: 3 }} onClick={() => navigate(`/p/${pid}/twin`)}>Explore <Icon name="arrow" size={13} /></button>
          <div style={{ position: 'absolute', inset: '56px 0 0 0' }}>
            <GraphView nodes={moduleGraph.nodes} edges={moduleGraph.edges} minimal onSelect={(id) => id && navigate(`/p/${pid}/twin?module=${encodeURIComponent(id)}`)} />
          </div>
        </div>
      </div>

      <div className="grid g3" style={{ marginBottom: 18 }}>
        <div className="card" data-reveal>
          <SectionTitle icon="target" title="Most critical components" sub="Transitive dependents × PageRank × complexity" />
          {s.critical.map((id, i) => {
            const u = twin.units[id];
            return (
              <div key={id} className="list-item" onClick={() => navigate(`/p/${pid}/twin?node=${encodeURIComponent(id)}`)}>
                <span className="num subtle" style={{ width: 16, fontWeight: 700 }}>{i + 1}</span>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }} className="ellipsis">{u.name}</div>
                  <div className="tiny subtle">{u.metrics.dependents_transitive} dependents · fan-in {u.metrics.fan_in}</div>
                </div>
                <LayerTag layer={u.layer} small />
              </div>
            );
          })}
        </div>
        <div className="card" data-reveal>
          <SectionTitle icon="bug" title="Risk dashboard" sub="Defect-prone hotspots" right={<button className="btn btn-ghost btn-sm" onClick={() => navigate(`/p/${pid}/debt`)}>All</button>} />
          {Object.values(twin.units).filter((u) => !u.is_test && u.risk.level !== 'low').sort((a, b) => b.risk.score - a.risk.score).slice(0, 6).map((u) => (
            <div key={u.id} className="list-item" onClick={() => navigate(`/p/${pid}/twin?node=${encodeURIComponent(u.id)}`)}>
              <span className={`dot ${u.risk.level}`} />
              <div className="grow" style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{u.name}</div>
                <div className="tiny subtle ellipsis">{u.risk.reasons.slice(0, 2).join(' · ')}</div>
              </div>
              <span className="num small" style={{ color: RISK_COLORS[u.risk.level], fontWeight: 700 }}>{Math.round(u.risk.score * 100)}</span>
            </div>
          ))}
        </div>
        <div className="card" data-reveal>
          <SectionTitle icon="layers" title="Composition" sub={`${c.units} components by architectural layer`} />
          <div className="row" style={{ height: 12, borderRadius: 99, overflow: 'hidden', gap: 2, marginBottom: 14 }}>
            {layers.map(([l, n]) => <div key={l} title={`${LAYER_LABEL[l] || l}: ${n}`} style={{ width: `${(n / totalLayer) * 100}%`, height: '100%', background: LAYER_COLORS[l] || '#8e8e93' }} />)}
          </div>
          <div className="grid g2" style={{ gap: 8 }}>
            {layers.slice(0, 12).map(([l, n]) => <div key={l} className="row between small"><LayerTag layer={l} small /><b className="num">{n}</b></div>)}
          </div>
          <hr className="divider" />
          <div className="row between small"><span className="muted">Technical debt</span><b>{twin.debt.level} · {twin.debt.hours} h</b></div>
          <div className="row between small" style={{ marginTop: 6 }}><span className="muted">Findings</span><b>{twin.issues.length}</b></div>
          {twin.history?.available && <div className="row between small" style={{ marginTop: 6 }}><span className="muted">Commits analysed</span><b>{twin.history.commits}</b></div>}
        </div>
      </div>

      <div className="grid g3">
        <div className="card span2" data-reveal>
          <SectionTitle icon="alert" title="Needs attention" sub="Highest-severity findings" right={<button className="btn btn-ghost btn-sm" onClick={() => navigate(`/p/${pid}/health`)}>All findings</button>} />
          <div className="col" style={{ gap: 8 }}>
            {topIssues.map((i) => (
              <div key={i.id} className="issue clickable" onClick={() => openCode(i.file, i.line)}>
                <RiskBadge level={i.severity} />
                <div className="grow" style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>{i.title}</div>
                  <div className="small muted">{i.detail}</div>
                  <div className="tiny subtle" style={{ marginTop: 3 }}>{i.file}:{i.line}{i.principle ? ` · ${i.principle}` : ''}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="col" style={{ gap: 18 }}>
          <div className="card" data-reveal>
            <SectionTitle icon="sparkle" title="Ask CodeTwin" sub="Grounded in this project's code" />
            <div className="col" style={{ gap: 6 }}>
              {SUGGESTED.slice(0, 5).map((q) => (
                <div key={q} className="list-item" style={{ padding: '8px 10px' }} onClick={() => navigate(`/p/${pid}/ask?q=${encodeURIComponent(q)}`)}>
                  <Icon name="chat" size={15} style={{ color: 'var(--blue)' }} /><span className="grow small">{q}</span><Icon name="chevron" size={14} style={{ color: 'var(--text-3)' }} />
                </div>
              ))}
            </div>
          </div>
          <div className="card" data-reveal>
            <SectionTitle icon="api" title="Unused APIs & dead code" />
            {s.unused_endpoints.slice(0, 5).map((id) => {
              const e = twin.endpoints[id];
              return <div key={id} className="row small" style={{ padding: '5px 0' }}><span className="badge neutral mono">{e.method}</span><span className="mono ellipsis grow">{e.path}</span></div>;
            })}
            {s.possibly_dead.slice(0, 4).map((id) => (
              <div key={id} className="row small clickable" style={{ padding: '5px 0' }} onClick={() => openCode(twin.units[id].file)}>
                <span className="badge medium">unused</span><span className="ellipsis">{twin.units[id].name}</span><span className="tiny subtle">{modName(twin.units[id].module)}</span>
              </div>
            ))}
            {!s.unused_endpoints.length && !s.possibly_dead.length && <div className="small muted">Nothing found 🎉</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
