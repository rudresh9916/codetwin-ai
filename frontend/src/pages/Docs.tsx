import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { gsap } from '../lib/anim';
import { useProject } from '../lib/store';
import Icon from '../components/Icon';
import Markdown from '../components/Markdown';
import { Spinner } from '../components/Common';

export default function Docs() {
  const { meta } = useProject();
  const pid = meta!.id;
  const [docs, setDocs] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>('load');
  const [active, setActive] = useState('overview');
  const body = useRef<HTMLDivElement>(null);

  const load = async (ai = false, refresh = false) => {
    setBusy(ai ? 'ai' : refresh ? 'refresh' : 'load');
    try { setDocs(await api.docs(pid, ai, refresh)); } finally { setBusy(null); }
  };
  useEffect(() => { load(); }, [pid]);
  useEffect(() => {
    if (docs && body.current) gsap.fromTo(body.current.querySelectorAll('section'), { y: 16, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, stagger: 0.06, ease: 'power3.out' });
  }, [docs]);
  useEffect(() => {
    const onScroll = () => {
      const secs = body.current?.querySelectorAll('section[id]') || [];
      let cur = active;
      secs.forEach((s) => { if ((s as HTMLElement).getBoundingClientRect().top < 160) cur = s.id; });
      setActive(cur);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [docs]);

  return (
    <div className="page">
      <div className="page-header">
        <div><div className="eyebrow">README · API · UML · sequence diagrams · onboarding</div><h1 className="h1">Documentation</h1></div>
        <div className="row">
          <button className="btn btn-outline btn-sm" onClick={() => load(false, true)} disabled={!!busy}>{busy === 'refresh' ? <Spinner size={12} /> : <Icon name="refresh" size={14} />}Regenerate</button>
          <button className="btn btn-grad btn-sm" onClick={() => load(true, true)} disabled={!!busy}>{busy === 'ai' ? <Spinner size={12} /> : <Icon name="sparkle" size={14} />}Write with AI</button>
          <a className="btn btn-primary btn-sm" href={api.docsExportUrl(pid)}><Icon name="download" size={14} />Download .md</a>
        </div>
      </div>
      {!docs ? <div className="card"><div className="row muted"><Spinner />Generating documentation…</div></div> : (
        <div className="grid" style={{ gridTemplateColumns: '220px minmax(0, 1fr)', gap: 24, alignItems: 'start' }}>
          <div className="card" style={{ position: 'sticky', top: 76, padding: 10 }}>
            {docs.sections.map((s: any) => (
              <div key={s.id} className={`nav-item ${active === s.id ? 'active' : ''}`} style={{ fontSize: 13 }}
                onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{s.title}</div>
            ))}
            {docs.ai && <div className="badge purple" style={{ margin: '10px 8px 4px' }}><Icon name="sparkle" size={11} />AI-written</div>}
          </div>
          <div ref={body} className="col" style={{ gap: 18 }}>
            {docs.sections.map((s: any) => (
              <section key={s.id} id={s.id} className="card" style={{ padding: 28, scrollMarginTop: 76 }}>
                <h2 className="h2" style={{ marginBottom: 14 }}>{s.title}</h2>
                <Markdown text={s.markdown} />
              </section>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
