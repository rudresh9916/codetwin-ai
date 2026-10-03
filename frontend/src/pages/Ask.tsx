import { useEffect, useRef, useState } from 'react';
import { api, streamSSE } from '../lib/api';
import { gsap } from '../lib/anim';
import { useProject, useTwin } from '../lib/store';
import { useRouter } from '../lib/router';
import { LAYER_COLORS } from '../lib/ui';
import Icon from '../components/Icon';
import Markdown from '../components/Markdown';
import { Spinner } from '../components/Common';
import { SUGGESTED } from './Overview';

interface Msg { role: 'user' | 'assistant'; content: string; sources?: any[]; mode?: string; facts?: string[]; streaming?: boolean }

export default function Ask() {
  const twin = useTwin();
  const { meta, openCode } = useProject();
  const { loc, navigate } = useRouter();
  const pid = meta!.id;
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [showFacts, setShowFacts] = useState<number | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  useEffect(() => {
    let alive = true;
    api.chatHistory(pid).then((h) => {
      if (!alive) return;
      const q = loc.query.get('q');
      if (q && !started.current) { started.current = true; navigate(`/p/${pid}/ask`, true); send(q, h as Msg[]); }
      else if (!started.current) setMsgs(h as Msg[]);
    });
    return () => { alive = false; };
  }, [pid]);
  useEffect(() => { scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: 'smooth' }); }, [msgs]);
  useEffect(() => {
    const last = scroll.current?.querySelector('.msg:last-child');
    if (last) gsap.fromTo(last, { y: 12, opacity: 0 }, { y: 0, opacity: 1, duration: 0.45, ease: 'power3.out' });
  }, [msgs.length]);

  async function send(text: string, base?: Msg[]) {
    const q = text.trim();
    if (!q || busy) return;
    setInput('');
    setBusy(true);
    const history = base ?? msgs;
    const next: Msg[] = [...history, { role: 'user', content: q }, { role: 'assistant', content: '', streaming: true }];
    setMsgs(next);
    started.current = true;
    const update = (fn: (m: Msg) => Msg) => setMsgs((cur) => {
      const c = [...cur];
      const last = c[c.length - 1];
      if (!last || last.role !== 'assistant') c.push(fn({ role: 'assistant', content: '', streaming: true }));
      else c[c.length - 1] = fn(last);
      return c;
    });
    try {
      await streamSSE(`/api/projects/${pid}/chat`, { message: q }, (ev) => {
        if (ev.type === 'meta') update((m) => ({ ...m, sources: ev.sources, mode: ev.mode, facts: ev.facts }));
        else if (ev.type === 'token') update((m) => ({ ...m, content: m.content + ev.text }));
        else if (ev.type === 'error') update((m) => ({ ...m, content: m.content + `\n\n> ${ev.message}` }));
      });
    } catch (e: any) {
      update((m) => ({ ...m, content: `> ${e.message}` }));
    }
    update((m) => ({ ...m, streaming: false }));
    setBusy(false);
  }

  const cite = (m: Msg, n: number) => { const s = m.sources?.find((x) => x.n === n); if (s) openCode(s.file, s.start, s.end); };

  return (
    <div className="page" style={{ paddingBottom: 16 }}>
      <div className="page-header" style={{ marginBottom: 10 }}>
        <div><div className="eyebrow">Retrieval-augmented, grounded in the Digital Twin</div><h1 className="h1">Ask CodeTwin</h1></div>
        {msgs.length > 0 && <button className="btn btn-secondary btn-sm" onClick={async () => { await api.clearChat(pid); setMsgs([]); }}><Icon name="trash" size={14} />Clear</button>}
      </div>
      <div className="chat">
        <div className="chat-scroll" ref={scroll}>
          {msgs.length === 0 && (
            <div style={{ textAlign: 'center', padding: '6vh 0 20px' }}>
              <div className="avatar" style={{ width: 64, height: 64, borderRadius: 20, margin: '0 auto 16px', boxShadow: '0 12px 30px rgba(94,92,230,.35)' }}><Icon name="sparkle" size={30} /></div>
              <div className="h2">What would you like to know about {twin.name}?</div>
              <div className="muted" style={{ margin: '8px auto 22px', maxWidth: 560 }}>
                Answers combine static-analysis facts (dependency graph, metrics, impact) with the most relevant code, and cite their sources.
              </div>
              <div className="suggestions">{SUGGESTED.map((s) => <span key={s} className="chip" style={{ height: 34, fontSize: 13.5 }} onClick={() => send(s)}>{s}</span>)}</div>
            </div>
          )}
          {msgs.map((m, i) => m.role === 'user' ? (
            <div key={i} className="msg user"><div className="bubble-user">{m.content}</div></div>
          ) : (
            <div key={i} className="msg">
              <div className="avatar"><Icon name="sparkle" size={16} /></div>
              <div className="bubble-ai">
                <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                  <b className="small">CodeTwin</b>
                  {m.mode && <span className={`badge ${m.mode === 'offline' ? 'neutral' : 'purple'}`}>{m.mode === 'offline' ? 'Offline · twin facts' : m.mode === 'anthropic' ? 'Claude' : m.mode}</span>}
                  {m.facts && m.facts.length > 0 && <span className="badge blue clickable" onClick={() => setShowFacts(showFacts === i ? null : i)}>{m.facts.length} twin facts</span>}
                </div>
                {showFacts === i && m.facts && (
                  <div className="callout" style={{ flexDirection: 'column', gap: 4, marginBottom: 10 }}>
                    {m.facts.map((f, k) => <div key={k} className="small" style={{ whiteSpace: 'pre-wrap' }}>• {f}</div>)}
                  </div>
                )}
                {m.content ? <Markdown text={m.content} onCite={(n) => cite(m, n)} /> : <div className="row small muted"><Spinner size={13} />Reading the twin…</div>}
                {m.streaming && m.content && <span className="caret" />}
                {m.sources && m.sources.length > 0 && !m.streaming && (
                  <div className="grid g2" style={{ gap: 8, marginTop: 12 }}>
                    {m.sources.slice(0, 6).map((s) => {
                      const u = s.unit ? twin.units[s.unit] : null;
                      return (
                        <div key={s.n} className="source" onClick={() => openCode(s.file, s.start, s.end)}>
                          <span className="cite" style={{ flex: 'none' }}>{s.n}</span>
                          <div style={{ minWidth: 0 }}>
                            <div className="small ellipsis" style={{ fontWeight: 600 }}>{s.name}</div>
                            <div className="tiny subtle ellipsis">{s.file}:{s.start}</div>
                          </div>
                          {u && <span className="dot" style={{ background: LAYER_COLORS[u.layer], marginLeft: 'auto' }} />}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="composer">
          <textarea rows={1} placeholder="Ask about architecture, flows, impact, risks…" value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }} />
          <button className="btn btn-primary btn-icon" style={{ borderRadius: 14 }} disabled={busy || !input.trim()} onClick={() => send(input)}>
            {busy ? <Spinner size={14} /> : <Icon name="send" size={16} />}
          </button>
        </div>
      </div>
    </div>
  );
}
