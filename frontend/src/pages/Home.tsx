import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { gsap, useScrollReveal } from '../lib/anim';
import { useRouter } from '../lib/router';
import type { ProjectMeta } from '../lib/types';
import { scoreColor, timeAgo } from '../lib/ui';
import Icon from '../components/Icon';
import { Segmented, Spinner } from '../components/Common';
import { Logo, ThemeToggle } from '../components/Brand';

/** Animated "living graph" behind the hero. */
function NetworkCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current!;
    const ctx = c.getContext('2d')!;
    let w = 0, h = 0, raf = 0;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const colors = ['#0a84ff', '#5e5ce6', '#bf5af2', '#30d158', '#ff9f0a', '#64d2ff'];
    const N = 46;
    const pts = Array.from({ length: N }, (_, i) => ({ x: Math.random(), y: Math.random(), vx: (Math.random() - 0.5) * 0.00045, vy: (Math.random() - 0.5) * 0.00045,
      r: 2 + Math.random() * 3.5, c: colors[i % colors.length], pulse: Math.random() * Math.PI * 2 }));
    const resize = () => { w = c.clientWidth; h = c.clientHeight; c.width = w * dpr; c.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
    resize();
    window.addEventListener('resize', resize);
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h);
      const dark = document.documentElement.dataset.theme === 'dark';
      for (const p of pts) {
        if (!reduced) { p.x += p.vx; p.y += p.vy; }
        if (p.x < 0 || p.x > 1) p.vx *= -1;
        if (p.y < 0 || p.y > 1) p.vy *= -1;
      }
      for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
        const a = pts[i], b = pts[j];
        const dx = (a.x - b.x) * w, dy = (a.y - b.y) * h;
        const d = Math.sqrt(dx * dx + dy * dy);
        if (d < 170) {
          ctx.strokeStyle = dark ? `rgba(255,255,255,${0.12 * (1 - d / 170)})` : `rgba(0,0,0,${0.08 * (1 - d / 170)})`;
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(a.x * w, a.y * h); ctx.lineTo(b.x * w, b.y * h); ctx.stroke();
        }
      }
      for (const p of pts) {
        const s = 1 + 0.25 * Math.sin(t / 700 + p.pulse);
        ctx.fillStyle = p.c;
        ctx.globalAlpha = 0.75;
        ctx.beginPath(); ctx.arc(p.x * w, p.y * h, p.r * s, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 0.12;
        ctx.beginPath(); ctx.arc(p.x * w, p.y * h, p.r * s * 3.2, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize); };
  }, []);
  return <canvas ref={ref} className="hero-canvas" />;
}

const FEATURES = [
  { icon: 'twin', color: '#0a84ff', title: 'Living Digital Twin', text: 'Real ASTs (javac + TypeScript compiler) turn your repository into an interactive graph of modules, classes, APIs and tables.' },
  { icon: 'impact', color: '#ff375f', title: 'Change Impact Prediction', text: '“If I modify UserService, what breaks?” — dependency propagation through services, endpoints, frontend and data.' },
  { icon: 'whatif', color: '#bf5af2', title: 'What-If Simulation', text: 'Remove, replace or extract a component — or split the monolith into microservices — and see latency, cost and risk first.' },
  { icon: 'health', color: '#30d158', title: 'Architecture Health', text: 'Eight measurable dimensions — modularity, coupling, complexity, security and more — never made up by an LLM.' },
  { icon: 'debt', color: '#ff9f0a', title: 'Debt & Bug Prediction', text: 'Hotspots from complexity × change frequency × centrality, SQALE debt estimates and a heatmap of where to look first.' },
  { icon: 'chat', color: '#5e5ce6', title: 'Ask Your Codebase', text: 'Hybrid RAG grounded in the twin: answers cite the exact classes, methods and request flows of your project.' },
];

export default function Home() {
  const { navigate } = useRouter();
  const [mode, setMode] = useState<'sample' | 'git' | 'zip' | 'local'>('sample');
  const [url, setUrl] = useState('');
  const [path, setPath] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [projects, setProjects] = useState<ProjectMeta[] | null>(null);
  const hero = useRef<HTMLDivElement>(null);
  const page = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  useScrollReveal(page);

  const [isPublic, setIsPublic] = useState(false);
  useEffect(() => { api.projects().then(setProjects).catch(() => setProjects([])); api.health().then((h) => setIsPublic(!!h.public)).catch(() => null); }, []);
  useLayoutEffect(() => {
    if (!hero.current) return;
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: 'power4.out' } });
      tl.fromTo('.hero .eyebrow', { y: 12, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6 })
        .fromTo('.hero .word', { yPercent: 110, opacity: 0, rotate: 2 }, { yPercent: 0, opacity: 1, rotate: 0, duration: 1.1, stagger: 0.09 }, '-=0.3')
        .fromTo('.hero .lead', { y: 16, opacity: 0 }, { y: 0, opacity: 1, duration: 0.8 }, '-=0.7')
        .fromTo('.import-card', { y: 40, opacity: 0, scale: 0.97 }, { y: 0, opacity: 1, scale: 1, duration: 1 }, '-=0.6')
        .fromTo('.pipeline .step', { y: 10, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, stagger: 0.05 }, '-=0.6');
    }, hero);
    return () => ctx.revert();
  }, []);

  const go = async (fn: () => Promise<ProjectMeta>) => {
    setBusy(true); setErr(null);
    try { const m = await fn(); navigate(`/p/${m.id}`); } catch (e: any) { setErr(e.message); setBusy(false); }
  };
  const submit = () => {
    if (mode === 'sample') go(api.importSample);
    else if (mode === 'git') go(() => api.importGit(url));
    else if (mode === 'local') go(() => api.importLocal(path));
    else fileInput.current?.click();
  };
  const onFile = (f?: File | null) => { if (f) go(() => api.upload(f)); };

  return (
    <div className="landing" ref={page}>
      <div className="landing-nav">
        <div className="brand" style={{ padding: 0 }}><Logo size={26} /> CodeTwin <span className="grad-text">AI</span></div>
        <div className="grow" />
        <a className="small muted" href="#features" onClick={(e) => { e.preventDefault(); document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' }); }}>Features</a>
        <a className="small muted" href="/settings" onClick={(e) => { e.preventDefault(); navigate('/settings'); }}>Settings</a>
        <ThemeToggle />
      </div>

      <section className="hero" ref={hero}>
        <NetworkCanvas />
        <div className="hero-content">
          <div className="eyebrow" style={{ marginBottom: 18 }}>Intelligent Software Engineering Digital Twin</div>
          <h1 className="display">
            {['Understand.', 'Predict.'].map((w) => <span key={w} style={{ display: 'inline-block', overflow: 'hidden', verticalAlign: 'top', paddingBottom: 6 }}><span className="word">{w}&nbsp;</span></span>)}
            <span style={{ display: 'inline-block', overflow: 'hidden', verticalAlign: 'top', paddingBottom: 6 }}><span className="word grad-text">Improve.</span></span>
          </h1>
          <p className="lead" style={{ maxWidth: 680, margin: '22px auto 0' }}>
            Give CodeTwin a repository. It builds a live model of your architecture, predicts what a change will break, and tells you how to make it better — before problems happen.
          </p>

          <div className="import-card">
            <div className="row between wrap" style={{ marginBottom: 16, gap: 12 }}>
              <div className="h3">Create a Digital Twin</div>
              <Segmented value={mode} onChange={(v) => { setMode(v); setErr(null); }} options={[
                { value: 'sample', label: 'Sample' }, { value: 'git', label: 'GitHub' }, { value: 'zip', label: 'ZIP' },
                ...(isPublic ? [] : [{ value: 'local' as const, label: 'Local folder' }])]} />
            </div>
            {mode === 'sample' && (
              <div className="row" style={{ gap: 14, padding: '6px 2px 14px' }}>
                <div className="stat-icon" style={{ background: 'var(--blue-soft)', color: 'var(--blue)', margin: 0 }}><Icon name="cube" /></div>
                <div className="grow">
                  <div style={{ fontWeight: 600 }}>ShopVerse — Spring Boot + React e-commerce</div>
                  <div className="small muted">46 Java classes, 24 TypeScript modules, PostgreSQL, Stripe, 37 commits of history. Perfect for the demo.</div>
                </div>
              </div>
            )}
            {mode === 'git' && (
              <div style={{ paddingBottom: 14 }}>
                <input className="input input-lg" placeholder="https://github.com/owner/repository" value={url} onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && submit()} />
                <div className="tiny subtle" style={{ marginTop: 8 }}>{isPublic
                  ? 'Public repositories on GitHub, GitLab or Bitbucket. Java, JavaScript and TypeScript are analysed.'
                  : 'Public repositories clone directly. For private ones use an access-token URL. Java, JavaScript and TypeScript are analysed.'}</div>
              </div>
            )}
            {mode === 'local' && (
              <div style={{ paddingBottom: 14 }}>
                <input className="input input-lg" placeholder="/Users/you/projects/my-app" value={path} onChange={(e) => setPath(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && submit()} />
                <div className="tiny subtle" style={{ marginTop: 8 }}>A folder on the machine running the CodeTwin server (copied, never modified).</div>
              </div>
            )}
            {mode === 'zip' && (
              <div className={`dropzone ${drag ? 'drag' : ''}`} style={{ marginBottom: 14 }} onClick={() => fileInput.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files?.[0]); }}>
                <Icon name="upload" size={26} style={{ color: 'var(--blue)' }} />
                <div style={{ fontWeight: 600, marginTop: 8 }}>Drop a .zip of your project</div>
                <div className="small muted">or click to browse — include the .git folder for history analysis</div>
              </div>
            )}
            <input ref={fileInput} type="file" accept=".zip" hidden onChange={(e) => onFile(e.target.files?.[0])} />
            {err && <div className="callout danger" style={{ marginBottom: 12 }}><Icon name="alert" size={16} />{err}</div>}
            <button className="btn btn-grad btn-lg" style={{ width: '100%' }} disabled={busy || (mode === 'git' && !url) || (mode === 'local' && !path)} onClick={submit}>
              {busy ? <><Spinner /> Preparing…</> : <>{mode === 'zip' ? 'Choose ZIP file' : 'Build Digital Twin'} <Icon name="arrow" size={17} /></>}
            </button>
          </div>

          <div className="pipeline">
            {['Repository', 'AST parsing', 'Dependency graph', 'Metrics', 'Digital Twin', 'RAG + LLM', 'Recommendations'].map((s, i, a) => (
              <span key={s} className="row" style={{ gap: 8 }}><span className="step">{s}</span>{i < a.length - 1 && <Icon name="arrow" size={14} className="arrow" />}</span>
            ))}
          </div>
        </div>
      </section>

      {projects && projects.length > 0 && (
        <section style={{ maxWidth: 1180, margin: '0 auto', padding: '30px 24px 10px' }}>
          <div className="row between" style={{ marginBottom: 14 }} data-scroll>
            <div className="h2">Your twins</div>
            <span className="small muted">{projects.length} project{projects.length > 1 ? 's' : ''}</span>
          </div>
          <div className="grid g3">
            {projects.map((p) => (
              <div key={p.id} className="card hover" data-scroll onClick={() => navigate(`/p/${p.id}`)}>
                <div className="row between">
                  <div className="row" style={{ minWidth: 0 }}>
                    <div className="stat-icon" style={{ background: 'var(--surface-2)', color: 'var(--text-2)', margin: 0 }}>
                      <Icon name={p.source?.type === 'git' ? 'github' : p.source?.type === 'zip' ? 'upload' : 'cube'} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 650 }} className="ellipsis">{p.name}</div>
                      <div className="tiny subtle">{timeAgo(p.updated_at)}</div>
                    </div>
                  </div>
                  {p.status === 'ready' && p.summary ? (
                    <div className="num" style={{ fontSize: 26, fontWeight: 700, color: scoreColor(p.summary.health) }}>{p.summary.health}</div>
                  ) : <span className={`badge ${p.status === 'error' ? 'high' : 'blue'}`}>{p.status}</span>}
                </div>
                {p.summary && (
                  <div className="small muted" style={{ marginTop: 12 }}>
                    {p.summary.counts.files} files · {p.summary.counts.units} components · {p.summary.counts.endpoints} APIs
                    <div className="row wrap" style={{ gap: 5, marginTop: 8 }}>
                      {(p.summary.frameworks || []).slice(0, 4).map((f: string) => <span key={f} className="badge neutral">{f}</span>)}
                    </div>
                  </div>
                )}
                {!isPublic && <button className="btn btn-ghost btn-sm" style={{ position: 'absolute', right: 10, bottom: 10 }} title="Delete"
                  onClick={async (e) => { e.stopPropagation(); if (confirm(`Delete ${p.name}?`)) { await api.deleteProject(p.id); setProjects(projects.filter((x) => x.id !== p.id)); } }}>
                  <Icon name="trash" size={14} />
                </button>}
              </div>
            ))}
          </div>
        </section>
      )}

      <section id="features" className="feature-grid">
        <div style={{ textAlign: 'center', marginBottom: 36 }} data-scroll>
          <div className="eyebrow">Beyond code review</div>
          <h2 className="h1" style={{ fontSize: 44, marginTop: 8 }}>Google Maps for your software system.</h2>
          <p className="lead" style={{ maxWidth: 720, margin: '14px auto 0' }}>Deterministic analysis understands structure. AI understands meaning. Together they form a twin you can question, stress-test and improve.</p>
        </div>
        <div className="grid g3">
          {FEATURES.map((f) => (
            <div key={f.title} className="feature" data-scroll>
              <div className="icon" style={{ background: f.color }}><Icon name={f.icon} size={21} /></div>
              <div className="h3" style={{ marginBottom: 6 }}>{f.title}</div>
              <div className="muted">{f.text}</div>
            </div>
          ))}
        </div>
        <div className="footer-note">CodeTwin AI · 7th-semester major project · Java & JS/TS analysis · Claude / OpenAI / Ollama</div>
      </section>
    </div>
  );
}
