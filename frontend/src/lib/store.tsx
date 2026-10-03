import { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from 'react';
import { api } from './api';
import type { ProjectMeta, Twin, Unit } from './types';

interface Ctx {
  meta: ProjectMeta | null;
  twin: Twin | null;
  error: string | null;
  reload: () => void;
  openCode: (file: string, line?: number, endLine?: number) => void;
  codeTarget: { file: string; line?: number; endLine?: number } | null;
  closeCode: () => void;
  toast: (msg: string) => void;
  index: { byName: Record<string, Unit>; dependents: Record<string, string[]>; dependencies: Record<string, string[]> };
}

const ProjectCtx = createContext<Ctx | null>(null);

export function ProjectProvider({ id, children, toast }: { id: string; children: ReactNode; toast: (m: string) => void }) {
  const [meta, setMeta] = useState<ProjectMeta | null>(null);
  const [twin, setTwin] = useState<Twin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [codeTarget, setCodeTarget] = useState<Ctx['codeTarget']>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    let timer: any;
    setError(null);
    const poll = async () => {
      try {
        const m = await api.project(id);
        if (!alive) return;
        setMeta(m);
        if (m.status === 'ready') {
          const t = await api.twin(id);
          if (alive) setTwin(t);
        } else if (m.status === 'error') {
          setError(m.error || 'Analysis failed');
        } else {
          timer = setTimeout(poll, 700);
        }
      } catch (e: any) {
        if (alive) setError(e.message);
      }
    };
    setTwin(null);
    poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [id, tick]);

  const index = useMemo(() => {
    const byName: Record<string, Unit> = {};
    const dependents: Record<string, string[]> = {};
    const dependencies: Record<string, string[]> = {};
    if (twin) {
      for (const u of Object.values(twin.units)) byName[u.name] = byName[u.name] || u;
      for (const e of twin.edges) {
        (dependents[e.target] = dependents[e.target] || []).push(e.source);
        (dependencies[e.source] = dependencies[e.source] || []).push(e.target);
      }
    }
    return { byName, dependents, dependencies };
  }, [twin]);

  const openCode = useCallback((file: string, line?: number, endLine?: number) => setCodeTarget({ file, line, endLine }), []);
  const value: Ctx = {
    meta, twin, error, reload: () => setTick((t) => t + 1), openCode, codeTarget, closeCode: () => setCodeTarget(null), toast, index,
  };
  return <ProjectCtx.Provider value={value}>{children}</ProjectCtx.Provider>;
}

export function useProject() {
  const c = useContext(ProjectCtx);
  if (!c) throw new Error('useProject outside provider');
  return c;
}

/** Twin is guaranteed in pages rendered after loading. */
export function useTwin(): Twin {
  return useProject().twin as Twin;
}

export function nodeName(twin: Twin, id: string): string {
  if (twin.units[id]) return twin.units[id].name;
  if (twin.endpoints[id]) return `${twin.endpoints[id].method} ${twin.endpoints[id].path}`;
  if (twin.tables[id]) return twin.tables[id].name;
  return id;
}
export function nodeLayer(twin: Twin, id: string): string {
  if (twin.units[id]) return twin.units[id].layer;
  if (twin.endpoints[id]) return 'endpoint';
  if (twin.tables[id]) return 'table';
  return 'module';
}
