import { createContext, useContext, useEffect, useState, ReactNode } from 'react';

/** Minimal history-API router (no dependency). */
interface Loc { path: string; query: URLSearchParams }
const RouterCtx = createContext<{ loc: Loc; navigate: (to: string, replace?: boolean) => void }>({
  loc: { path: '/', query: new URLSearchParams() }, navigate: () => {},
});

function current(): Loc {
  return { path: window.location.pathname || '/', query: new URLSearchParams(window.location.search) };
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [loc, setLoc] = useState<Loc>(current());
  useEffect(() => {
    const on = () => setLoc(current());
    window.addEventListener('popstate', on);
    return () => window.removeEventListener('popstate', on);
  }, []);
  const navigate = (to: string, replace = false) => {
    if (to === window.location.pathname + window.location.search) return;
    if (replace) window.history.replaceState({}, '', to); else window.history.pushState({}, '', to);
    setLoc(current());
    if (!replace) window.scrollTo({ top: 0 });
  };
  return <RouterCtx.Provider value={{ loc, navigate }}>{children}</RouterCtx.Provider>;
}

export const useRouter = () => useContext(RouterCtx);

export function match(pattern: string, path: string): Record<string, string> | null {
  const p = pattern.split('/').filter(Boolean);
  const s = path.split('/').filter(Boolean);
  if (p.length !== s.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < p.length; i++) {
    if (p[i].startsWith(':')) params[p[i].slice(1)] = decodeURIComponent(s[i]);
    else if (p[i] !== s[i]) return null;
  }
  return params;
}

export function Link({ to, children, className, style }: { to: string; children: ReactNode; className?: string; style?: any }) {
  const { navigate } = useRouter();
  return (
    <a href={to} className={className} style={style} onClick={(e) => { if (e.metaKey || e.ctrlKey) return; e.preventDefault(); navigate(to); }}>
      {children}
    </a>
  );
}
