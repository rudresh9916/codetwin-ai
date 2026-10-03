import { useEffect, useRef, useState } from 'react';
import { streamSSE } from '../lib/api';
import { gsap } from '../lib/anim';
import Icon from './Icon';
import Markdown from './Markdown';
import { Spinner } from './Common';

/** "Explain with AI" — streams an LLM (or deterministic offline) explanation of any analysis payload. */
export default function AIExplain({ pid, kind, payload, label = 'Explain with AI', auto = false }: { pid: string; kind: string; payload: any; label?: string; auto?: boolean }) {
  const [text, setText] = useState('');
  const [mode, setMode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const key = JSON.stringify(payload)?.length;
  useEffect(() => { setText(''); setMode(null); if (auto) run(); }, [key]);
  const run = async () => {
    setBusy(true); setText('');
    try {
      await streamSSE(`/api/projects/${pid}/explain`, { kind, payload }, (ev) => {
        if (ev.type === 'meta') setMode(ev.mode);
        if (ev.type === 'token') setText((t) => t + ev.text);
      });
    } catch (e: any) { setText(`> ${e.message}`); }
    setBusy(false);
  };
  useEffect(() => { if (mode && box.current) gsap.fromTo(box.current, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.4 }); }, [mode]);
  return (
    <div>
      {!text && !busy && <button className="btn btn-grad btn-sm" onClick={run}><Icon name="sparkle" size={14} />{label}</button>}
      {(text || busy) && (
        <div ref={box} className="card flat" style={{ background: 'var(--surface-2)', border: 0 }}>
          <div className="row" style={{ gap: 8, marginBottom: 8 }}>
            <div className="avatar" style={{ width: 24, height: 24, borderRadius: 7 }}><Icon name="sparkle" size={13} /></div>
            <b className="small">CodeTwin explains</b>
            {mode && <span className={`badge ${mode === 'offline' ? 'neutral' : 'purple'}`}>{mode === 'offline' ? 'Offline' : mode}</span>}
            {busy && <Spinner size={12} />}
            <div className="grow" />
            {!busy && <button className="btn btn-ghost btn-sm" onClick={run}><Icon name="refresh" size={13} />Regenerate</button>}
          </div>
          <Markdown text={text} />
        </div>
      )}
    </div>
  );
}
