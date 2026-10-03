import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { match, RouterProvider, useRouter } from './lib/router';
import { ProjectProvider, useProject } from './lib/store';
import { gsap } from './lib/anim';
import Icon from './components/Icon';
import { Toast } from './components/Common';
import { Logo, ThemeToggle } from './components/Brand';
import { CodeDrawer, Palette } from './components/Overlays';
import Home from './pages/Home';
import Settings from './pages/Settings';
import Analyzing from './pages/Analyzing';
import Overview from './pages/Overview';
import TwinPage from './pages/Twin';
import Explorer from './pages/Explorer';
import Ask from './pages/Ask';
import Impact from './pages/Impact';
import WhatIf from './pages/WhatIf';
import Health from './pages/Health';
import Debt from './pages/Debt';
import Refactor from './pages/Refactor';
import Evolution from './pages/Evolution';
import Docs from './pages/Docs';

const NAV = [
  { section: 'Understand' },
  { path: '', label: 'Overview', icon: 'overview' },
  { path: '/twin', label: 'Digital Twin', icon: 'twin' },
  { path: '/code', label: 'Code Explorer', icon: 'code' },
  { path: '/ask', label: 'Ask CodeTwin', icon: 'chat' },
  { section: 'Predict' },
  { path: '/impact', label: 'Impact Analysis', icon: 'impact' },
  { path: '/whatif', label: 'What-If Simulator', icon: 'whatif' },
  { path: '/debt', label: 'Tech Debt & Risk', icon: 'debt', badge: 'risk' },
  { section: 'Improve' },
  { path: '/health', label: 'Architecture Health', icon: 'health' },
  { path: '/refactor', label: 'Refactoring Advisor', icon: 'refactor', badge: 'ref' },
  { path: '/evolution', label: 'Evolution', icon: 'history' },
  { path: '/docs', label: 'Documentation', icon: 'docs' },
] as const;

function Sidebar({ pid, sub }: { pid: string; sub: string }) {
  const { navigate } = useRouter();
  const { twin, meta } = useProject();
  const badges: Record<string, number> = { risk: twin?.summary.counts.high_risk || 0, ref: twin?.refactorings.filter((r) => r.priority === 'high').length || 0 };
  return (
    <aside className="sidebar">
      <div className="brand" onClick={() => navigate('/')}><Logo /> CodeTwin<span className="grad-text">AI</span></div>
      <div className="sidebar-project">
        <div className="tiny subtle" style={{ fontWeight: 600, letterSpacing: '.04em', textTransform: 'uppercase' }}>Project</div>
        <div style={{ fontWeight: 650, marginTop: 2 }} className="ellipsis">{meta?.name || '…'}</div>
        {twin && <div className="tiny muted" style={{ marginTop: 2 }}>{twin.summary.counts.files} files · health {twin.health.overall}</div>}
      </div>
      <nav style={{ overflow: 'auto' }}>
        {NAV.map((n, i) => 'section' in n ? (
          <div key={i} className="nav-section">{n.section}</div>
        ) : (
          <div key={n.path} className={`nav-item ${sub === n.path ? 'active' : ''}`} onClick={() => navigate(`/p/${pid}${n.path}`)}>
            <Icon name={n.icon} size={17} />{n.label}
            {'badge' in n && n.badge && badges[n.badge] > 0 && <span className="nav-badge">{badges[n.badge]}</span>}
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">
        <div className="nav-item" onClick={() => navigate('/')}><Icon name="plus" size={17} />New analysis</div>
        <div className="nav-item" onClick={() => navigate('/settings')}><Icon name="settings" size={17} />Settings</div>
      </div>
    </aside>
  );
}

function Topbar({ title, onSearch }: { title: string; onSearch: () => void }) {
  const { meta } = useProject();
  return (
    <header className="topbar">
      <div className="crumbs"><span className="ellipsis">{meta?.name}</span><Icon name="chevron" size={13} /><b>{title}</b></div>
      <div className="search-trigger" onClick={onSearch}><Icon name="search" size={15} />Search components, files, code…<span className="kbd">⌘K</span></div>
      <ThemeToggle />
    </header>
  );
}

function ProjectRoutes({ pid, sub }: { pid: string; sub: string }) {
  const { twin, meta, error } = useProject();
  const [palette, setPalette] = useState(false);
  const pageRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette((p) => !p); } };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);
  useLayoutEffect(() => {
    if (pageRef.current) gsap.fromTo(pageRef.current, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.45, ease: 'power2.out', clearProps: 'transform' });
  }, [sub, !!twin]);
  const title = (NAV.find((n) => 'path' in n && n.path === sub) as any)?.label || 'Overview';
  let body;
  if (error) body = <Analyzing failed message={error} />;
  else if (!twin || !meta || meta.status !== 'ready') body = <Analyzing />;
  else {
    const pages: Record<string, any> = { '': Overview, '/twin': TwinPage, '/code': Explorer, '/ask': Ask, '/impact': Impact, '/whatif': WhatIf,
      '/health': Health, '/debt': Debt, '/refactor': Refactor, '/evolution': Evolution, '/docs': Docs };
    const P = pages[sub] || Overview;
    body = <P />;
  }
  return (
    <div className="shell">
      <Sidebar pid={pid} sub={sub} />
      <div className="main">
        <Topbar title={title} onSearch={() => setPalette(true)} />
        <div ref={pageRef} style={{ flex: 1 }}>{body}</div>
      </div>
      {palette && twin && <Palette onClose={() => setPalette(false)} />}
      <CodeDrawer />
    </div>
  );
}

function Routes() {
  const { loc } = useRouter();
  const [toast, setToast] = useState<string | null>(null);
  let content;
  const pm = match('/p/:id', loc.path) || match('/p/:id/:page', loc.path);
  if (pm) {
    const sub = pm.page ? `/${pm.page}` : '';
    content = (
      <ProjectProvider id={pm.id} toast={setToast}>
        <ProjectRoutes pid={pm.id} sub={sub} />
      </ProjectProvider>
    );
  } else if (loc.path === '/settings') {
    content = <Settings />;
  } else {
    content = <Home />;
  }
  return (
    <>
      {content}
      {toast && <Toast msg={toast} onDone={() => setToast(null)} />}
    </>
  );
}

export default function App() {
  return <RouterProvider><Routes /></RouterProvider>;
}
