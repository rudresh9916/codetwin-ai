import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../lib/api';
import { useProject } from '../lib/store';
import { useRouter } from '../lib/router';
import { gsap } from '../lib/anim';
import { LAYER_COLORS, LAYER_LABEL, short } from '../lib/ui';
import CodeView from './CodeView';
import Icon from './Icon';
import { Spinner } from './Common';

/** Slide-over code viewer opened from anywhere (sources, issues, nodes). */
export function CodeDrawer() {
  const { codeTarget, closeCode, meta, twin } = useProject();
  const [content, setContent] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const { navigate } = useRouter();
  useEffect(() => {
    if (!codeTarget || !meta) return;
    setContent(null); setErr(null);
    api.source(meta.id, codeTarget.file).then((r) => setContent(r.content)).catch((e) => setErr(e.message));
  }, [codeTarget?.file, meta?.id]);
  useEffect(() => {
    if (codeTarget && panel.current) gsap.fromTo(panel.current, { x: 60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.45, ease: 'power3.out' });
  }, [!!codeTarget]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') closeCode(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);
  if (!codeTarget) return null;
  const units = twin ? Object.values(twin.units).filter((u) => u.file === codeTarget.file) : [];
  return (
    <>
      <div className="overlay" style={{ background: 'rgba(0,0,0,.18)', backdropFilter: 'none' }} onClick={closeCode} />
      <div className="drawer" ref={panel}>
        <div className="code-head">
          <Icon name="file" size={16} />
          <div className="grow">
            <div style={{ fontWeight: 600 }} className="ellipsis">{short(codeTarget.file)}</div>
            <div className="tiny subtle ellipsis">{codeTarget.file}</div>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => { closeCode(); navigate(`/p/${meta!.id}/code?file=${encodeURIComponent(codeTarget.file)}&line=${codeTarget.line || 1}`); }}>
            Open in Explorer
          </button>
          <button className="btn btn-secondary btn-icon btn-sm" onClick={closeCode}><Icon name="x" size={15} /></button>
        </div>
        {units.length > 0 && (
          <div className="row wrap" style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', gap: 6 }}>
            {units.map((u) => (
              <span key={u.id} className="chip" onClick={() => { closeCode(); navigate(`/p/${meta!.id}/twin?node=${encodeURIComponent(u.id)}`); }}>
                <span className="dot" style={{ background: LAYER_COLORS[u.layer] }} />{u.name} · {LAYER_LABEL[u.layer]}
              </span>
            ))}
          </div>
        )}
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          {err && <div className="empty">{err}</div>}
          {!content && !err && <div className="empty"><Spinner /></div>}
          {content !== null && <CodeView path={codeTarget.file} content={content} line={codeTarget.line} endLine={codeTarget.endLine} className="grow" />}
        </div>
      </div>
    </>
  );
}

/** ⌘K command palette: jump to components, files, endpoints, pages — or run a semantic code search. */
export function Palette({ onClose }: { onClose: () => void }) {
  const { twin, meta, openCode } = useProject();
  const { navigate } = useRouter();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const [semantic, setSemantic] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const pid = meta?.id;
  useEffect(() => { if (box.current) gsap.fromTo(box.current, { y: -10, opacity: 0, scale: 0.98 }, { y: 0, opacity: 1, scale: 1, duration: 0.3, ease: 'power3.out' }); }, []);
  const pages = [
    ['Overview', ''], ['Digital Twin', '/twin'], ['Code Explorer', '/code'], ['Ask CodeTwin', '/ask'], ['Impact Analysis', '/impact'],
    ['What-If Simulator', '/whatif'], ['Architecture Health', '/health'], ['Tech Debt & Risk', '/debt'], ['Refactoring Advisor', '/refactor'],
    ['Evolution', '/evolution'], ['Documentation', '/docs'],
  ];
  const items = useMemo(() => {
    const s = q.toLowerCase().trim();
    const out: { key: string; label: string; sub: string; color: string; tag: string; run: () => void }[] = [];
    if (!twin || !pid) return out;
    for (const [label, path] of pages) if (!s || label.toLowerCase().includes(s)) out.push({ key: 'p' + path, label, sub: 'Go to page', color: '#8e8e93', tag: 'Page', run: () => navigate(`/p/${pid}${path}`) });
    if (s) {
      for (const u of Object.values(twin.units)) {
        if (u.name.toLowerCase().includes(s) || u.file.toLowerCase().includes(s))
          out.push({ key: u.id, label: u.name, sub: u.file, color: LAYER_COLORS[u.layer], tag: LAYER_LABEL[u.layer] || u.layer, run: () => navigate(`/p/${pid}/twin?node=${encodeURIComponent(u.id)}`) });
      }
      for (const e of Object.values(twin.endpoints)) {
        const l = `${e.method} ${e.path}`;
        if (l.toLowerCase().includes(s)) out.push({ key: e.id, label: l, sub: twin.units[e.unit]?.name || '', color: LAYER_COLORS.endpoint, tag: 'Endpoint', run: () => openCode(e.file, e.line) });
      }
    }
    return out.slice(0, 40);
  }, [q, twin]);
  const runSemantic = async () => {
    if (!pid || !q.trim()) return;
    setLoading(true);
    try { setSemantic((await api.search(pid, q, 12)).results); } finally { setLoading(false); }
  };
  const total = items.length;
  return (
    <div className="overlay" onMouseDown={onClose}>
      <div className="palette" ref={box} onMouseDown={(e) => e.stopPropagation()}>
        <input autoFocus placeholder="Jump to a component, endpoint or page — Enter ⇧ for semantic code search" value={q}
          onChange={(e) => { setQ(e.target.value); setSel(0); setSemantic(null); }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onClose();
            if (e.key === 'ArrowDown') { setSel((x) => Math.min(total - 1, x + 1)); e.preventDefault(); }
            if (e.key === 'ArrowUp') { setSel((x) => Math.max(0, x - 1)); e.preventDefault(); }
            if (e.key === 'Enter') {
              if (e.shiftKey || total === 0) runSemantic();
              else if (items[sel]) { items[sel].run(); onClose(); }
            }
          }} />
        <div className="palette-list">
          {items.map((it, i) => (
            <div key={it.key} className={`palette-item ${i === sel ? 'sel' : ''}`} onMouseEnter={() => setSel(i)} onClick={() => { it.run(); onClose(); }}>
              <span className="dot" style={{ background: it.color }} />
              <div className="grow"><div style={{ fontWeight: 600 }}>{it.label}</div><div className="tiny subtle ellipsis">{it.sub}</div></div>
              <span className="tiny muted">{it.tag}</span>
            </div>
          ))}
          {q.trim() && (
            <div className="palette-item" onClick={runSemantic} style={{ color: 'var(--blue)' }}>
              <Icon name="sparkle" size={16} />
              <div className="grow" style={{ fontWeight: 600 }}>Semantic search code for “{q}”</div>
              {loading ? <Spinner /> : <span className="kbd">⇧ Enter</span>}
            </div>
          )}
          {semantic && semantic.map((r) => (
            <div key={r.id} className="palette-item" onClick={() => { openCode(r.file, r.start, r.end); onClose(); }}>
              <Icon name={r.kind === 'api' ? 'api' : r.kind === 'doc' ? 'docs' : 'code'} size={16} />
              <div className="grow" style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{r.name}</div>
                <div className="tiny subtle ellipsis">{r.file}:{r.start} · {r.meta}</div>
              </div>
              <span className="tiny muted">{r.kind}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
