import type { ProjectMeta, Twin } from './types';

const BASE = (import.meta as any).env?.VITE_API_BASE || '';

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    ...opts,
    headers: opts.body && !(opts.body instanceof FormData) ? { 'content-type': 'application/json', ...(opts.headers || {}) } : opts.headers,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  health: () => req<any>('/api/health'),
  settings: () => req<any>('/api/settings'),
  saveSettings: (s: any) => req<any>('/api/settings', { method: 'PUT', body: JSON.stringify(s) }),
  testSettings: () => req<any>('/api/settings/test', { method: 'POST' }),
  projects: () => req<ProjectMeta[]>('/api/projects'),
  project: (id: string) => req<ProjectMeta>(`/api/projects/${id}`),
  deleteProject: (id: string) => req<any>(`/api/projects/${id}`, { method: 'DELETE' }),
  reanalyze: (id: string) => req<ProjectMeta>(`/api/projects/${id}/reanalyze`, { method: 'POST' }),
  importSample: () => req<ProjectMeta>('/api/projects/sample', { method: 'POST', body: JSON.stringify({ sample: 'shopverse' }) }),
  importGit: (url: string, branch?: string) => req<ProjectMeta>('/api/projects/git', { method: 'POST', body: JSON.stringify({ url, branch }) }),
  importLocal: (path: string) => req<ProjectMeta>('/api/projects/local', { method: 'POST', body: JSON.stringify({ path }) }),
  upload: (file: File) => { const fd = new FormData(); fd.append('file', file); return req<ProjectMeta>('/api/projects/upload', { method: 'POST', body: fd }); },
  twin: (id: string) => req<Twin>(`/api/projects/${id}/twin`),
  source: (id: string, path: string) => req<{ path: string; content: string }>(`/api/projects/${id}/source?path=${encodeURIComponent(path)}`),
  search: (id: string, q: string, k = 20) => req<any>(`/api/projects/${id}/search?q=${encodeURIComponent(q)}&k=${k}`),
  impact: (id: string, body: any) => req<any>(`/api/projects/${id}/impact`, { method: 'POST', body: JSON.stringify(body) }),
  whatif: (id: string, body: any) => req<any>(`/api/projects/${id}/whatif`, { method: 'POST', body: JSON.stringify(body) }),
  chatHistory: (id: string) => req<any[]>(`/api/projects/${id}/chat`),
  clearChat: (id: string) => req<any>(`/api/projects/${id}/chat`, { method: 'DELETE' }),
  docs: (id: string, ai = false, refresh = false) => req<any>(`/api/projects/${id}/docs?ai=${ai ? 1 : 0}&refresh=${refresh ? 1 : 0}`),
  evolution: (id: string) => req<any>(`/api/projects/${id}/evolution`),
  runEvolution: (id: string) => req<any>(`/api/projects/${id}/evolution?snapshots=6`, { method: 'POST' }),
  docsExportUrl: (id: string) => `${BASE}/api/projects/${id}/docs/export`,
  reportUrl: (id: string) => `${BASE}/api/projects/${id}/report`,
};

/** POST and consume a Server-Sent-Events stream. */
export async function streamSSE(path: string, body: any, onEvent: (ev: any) => void, signal?: AbortSignal) {
  const res = await fetch(BASE + path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal });
  if (!res.ok || !res.body) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = j.detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data:')) {
          try { onEvent(JSON.parse(line.slice(5).trim())); } catch { /* partial */ }
        }
      }
    }
  }
}
