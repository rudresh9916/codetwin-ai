import { useRef, useState } from 'react';
import { gsap, useReveal } from '../lib/anim';
import { useProject, useTwin } from '../lib/store';
import { useRouter } from '../lib/router';
import Icon from '../components/Icon';
import { Empty, RiskBadge } from '../components/Common';
import AIExplain from '../components/AIExplain';

const TYPE_ICON: Record<string, string> = { 'split-class': 'split', 'extract-method': 'code', 'break-cycle': 'refresh', 'introduce-service': 'layers',
  'remove-duplication': 'copy', 'externalize-state': 'db' };
const TYPE_LABEL: Record<string, string> = { 'split-class': 'Split class', 'extract-method': 'Extract method', 'break-cycle': 'Break cycle',
  'introduce-service': 'Introduce service', 'remove-duplication': 'Remove duplication', 'externalize-state': 'Externalise state' };

export default function Refactor() {
  const twin = useTwin();
  const { meta, openCode } = useProject();
  const { navigate } = useRouter();
  const pid = meta!.id;
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState<string | null>(twin.refactorings[0]?.id || null);
  useReveal(ref, []);
  const total = twin.refactorings.reduce((a, r) => a + r.effort_hours, 0);

  return (
    <div className="page" ref={ref}>
      <div className="page-header">
        <div><div className="eyebrow">Not just “long function detected”</div><h1 className="h1">Refactoring Advisor</h1>
          <div className="muted" style={{ marginTop: 6 }}>Concrete target designs derived from responsibility analysis, call graphs and cycles — each explained with the principle it restores.</div></div>
        <div className="row"><span className="badge neutral">{twin.refactorings.length} recommendations</span><span className="badge blue">~{total} h total</span></div>
      </div>
      {twin.refactorings.length === 0 && <div className="card"><Empty icon="check" title="No refactorings needed">The architecture looks clean.</Empty></div>}
      <div className="col" style={{ gap: 14 }}>
        {twin.refactorings.map((r) => {
          const isOpen = open === r.id;
          return (
            <div key={r.id} className="card" data-reveal style={{ padding: 0, overflow: 'hidden' }}>
              <div className="row clickable" style={{ padding: '16px 20px', gap: 14 }} onClick={(e) => {
                setOpen(isOpen ? null : r.id);
                const body = (e.currentTarget.parentElement as HTMLElement).querySelector('.ref-body');
                if (!isOpen && body) setTimeout(() => gsap.fromTo(body, { height: 0, opacity: 0 }, { height: 'auto', opacity: 1, duration: 0.45, ease: 'power3.out' }), 0);
              }}>
                <div className="stat-icon" style={{ margin: 0, background: r.priority === 'high' ? 'var(--red-soft)' : r.priority === 'medium' ? 'var(--orange-soft)' : 'var(--green-soft)',
                  color: r.priority === 'high' ? 'var(--red)' : r.priority === 'medium' ? 'var(--orange)' : 'var(--green)' }}><Icon name={TYPE_ICON[r.type] || 'refactor'} /></div>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="row" style={{ gap: 8 }}><b style={{ fontSize: 15 }}>{r.title}</b><RiskBadge level={r.priority} label={`${r.priority} priority`} /></div>
                  <div className="small muted ellipsis">{TYPE_LABEL[r.type]} · {r.principle} · ~{r.effort_hours} h</div>
                </div>
                <Icon name={isOpen ? 'down' : 'chevron'} size={16} style={{ color: 'var(--text-3)' }} />
              </div>
              {isOpen && (
                <div className="ref-body" style={{ padding: '0 20px 20px', borderTop: '1px solid var(--border)' }}>
                  <div className="grid g2" style={{ marginTop: 16 }}>
                    <div>
                      <div className="eyebrow" style={{ marginBottom: 6 }}>Problem</div>
                      <div>{r.problem}</div>
                      {r.notes.filter((n) => !n.includes('\n')).map((n) => <div key={n} className="callout warn small" style={{ marginTop: 10 }}><Icon name="alert" size={15} />{n}</div>)}
                      {r.notes.filter((n) => n.includes('\n')).map((n) => <pre key={n} className="md" style={{ marginTop: 10 }}><code className="small">{n}</code></pre>)}
                      <div className="eyebrow" style={{ margin: '16px 0 6px' }}>Recommendation</div>
                      <div>{r.suggestion}</div>
                      <div className="callout" style={{ marginTop: 12 }}><Icon name="check" size={15} /><span className="small"><b>Benefit:</b> {r.benefit}</span></div>
                    </div>
                    <div>
                      {r.proposed.length > 0 && (
                        <>
                          <div className="eyebrow" style={{ marginBottom: 8 }}>{r.type === 'extract-method' ? 'Proposed steps' : 'Proposed design'}</div>
                          <div className="col" style={{ gap: 8 }}>
                            {r.proposed.map((p, i) => (
                              <div key={p.name + i} className="issue" style={{ alignItems: 'center' }}>
                                <div style={{ width: 28, height: 28, borderRadius: 8, display: 'grid', placeItems: 'center', background: i === 0 && r.type === 'split-class' ? 'var(--blue)' : 'var(--surface-2)',
                                  color: i === 0 && r.type === 'split-class' ? '#fff' : 'var(--text-2)', fontWeight: 700, fontSize: 12, flex: 'none' }}>{i + 1}</div>
                                <div className="grow" style={{ minWidth: 0 }}>
                                  <div className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{p.name}{r.type === 'extract-method' ? '()' : ''}</div>
                                  <div className="tiny muted">{p.responsibility}{p.methods?.length ? ` · from ${p.methods.slice(0, 4).join(', ')}` : ''}{p.existing ? ' · existing service' : ''}</div>
                                </div>
                                {p.from_line && <button className="btn btn-ghost btn-sm" onClick={() => openCode(r.file, p.from_line)}>L{p.from_line}</button>}
                              </div>
                            ))}
                          </div>
                        </>
                      )}
                      <div className="row" style={{ gap: 6, marginTop: 14 }}>
                        <button className="btn btn-secondary btn-sm" onClick={() => openCode(r.file, r.line)}><Icon name="code" size={13} />View code</button>
                        {r.unit && <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/p/${pid}/impact?target=${encodeURIComponent(r.unit!)}`)}><Icon name="impact" size={13} />Impact of refactoring</button>}
                      </div>
                    </div>
                  </div>
                  <div style={{ marginTop: 16 }}>
                    <AIExplain pid={pid} kind="refactoring" payload={r} label="Explain & sketch the refactored code" />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
