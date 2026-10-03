import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { useReveal } from '../lib/anim';
import { useRouter } from '../lib/router';
import Icon from '../components/Icon';
import { Segmented, Spinner } from '../components/Common';
import { Logo, ThemeToggle } from '../components/Brand';

export default function Settings() {
  const { navigate } = useRouter();
  const [s, setS] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [test, setTest] = useState<any>(null);
  const [testing, setTesting] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useReveal(ref, [!!s]);
  useEffect(() => { api.settings().then(setS); api.health().then(setHealth).catch(() => null); }, []);
  const set = (k: string, v: any) => setS({ ...s, [k]: v });
  const save = async () => { setSaving(true); try { setS(await api.saveSettings(s)); setTest(null); } finally { setSaving(false); } };
  const runTest = async () => { setTesting(true); setTest(null); try { await api.saveSettings(s); setTest(await api.testSettings()); } finally { setTesting(false); } };

  return (
    <div className="landing">
      <div className="landing-nav">
        <div className="brand clickable" style={{ padding: 0 }} onClick={() => navigate('/')}><Logo size={26} /> CodeTwin <span className="grad-text">AI</span></div>
        <div className="grow" />
        <button className="btn btn-secondary btn-sm" onClick={() => window.history.length > 1 ? window.history.back() : navigate('/')}><Icon name="back" size={14} />Back</button>
        <ThemeToggle />
      </div>
      <div className="page" style={{ maxWidth: 860 }} ref={ref}>
        <div className="page-header"><div><div className="eyebrow">Preferences</div><h1 className="h1">Settings</h1></div></div>
        {!s ? <Spinner /> : (
          <div className="col" style={{ gap: 18 }}>
            {s.locked && <div className="callout"><Icon name="shield" size={16} />Settings are read-only on this public demo. The server owner configures AI with environment variables.</div>}
            <fieldset disabled={!!s.locked} className="col" style={{ gap: 18, border: 0, padding: 0, margin: 0, minWidth: 0 }}>
            <div className="card" data-reveal>
              <div className="h3" style={{ marginBottom: 4 }}>AI provider</div>
              <div className="small muted" style={{ marginBottom: 16 }}>
                Static analysis, metrics, impact and what-if simulation never need an LLM. The provider powers natural-language answers, explanations and AI-written docs.
              </div>
              <Segmented value={s.provider} onChange={(v) => set('provider', v)} options={[
                { value: 'anthropic', label: 'Claude' }, { value: 'openai', label: 'OpenAI' }, { value: 'ollama', label: 'Ollama (local)' }, { value: 'none', label: 'Offline' }]} />
              <div className="grid g2" style={{ marginTop: 18 }}>
                {s.provider === 'anthropic' && <>
                  <div><label className="label">Anthropic API key</label><input className="input" type="password" placeholder={s.anthropic_api_key_set ? s.anthropic_api_key : 'sk-ant-…'}
                    onChange={(e) => set('anthropic_api_key', e.target.value)} /></div>
                  <div><label className="label">Model</label><input className="input" list="claude-models" value={s.anthropic_model} onChange={(e) => set('anthropic_model', e.target.value)} />
                    <datalist id="claude-models">
                      <option value="claude-opus-5-5">Claude Opus 5.5 — most capable (default)</option>
                      <option value="claude-sonnet-5-5">Claude Sonnet 5.5 — faster, lower cost</option>
                      <option value="claude-haiku-4-5">Claude Haiku 4.5 — fastest, cheapest</option>
                    </datalist></div>
                  <div className="span2"><label className="label">Effort</label>
                    <Segmented value={s.anthropic_effort || 'medium'} onChange={(v) => set('anthropic_effort', v)} options={[
                      { value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }, { value: 'xhigh', label: 'Extra high' }]} />
                    <div className="tiny subtle" style={{ marginTop: 6 }}>How much Claude thinks before answering. Higher is more thorough but slower and costs more.</div></div>
                </>}
                {s.provider === 'openai' && <>
                  <div><label className="label">OpenAI API key</label><input className="input" type="password" placeholder={s.openai_api_key_set ? s.openai_api_key : 'sk-…'}
                    onChange={(e) => set('openai_api_key', e.target.value)} /></div>
                  <div><label className="label">Model</label><input className="input" value={s.openai_model} onChange={(e) => set('openai_model', e.target.value)} /></div>
                  <div className="span2"><label className="label">Base URL (OpenAI-compatible)</label><input className="input" value={s.openai_base_url} onChange={(e) => set('openai_base_url', e.target.value)} /></div>
                </>}
                {s.provider === 'ollama' && <>
                  <div><label className="label">Ollama URL</label><input className="input" value={s.ollama_url} onChange={(e) => set('ollama_url', e.target.value)} /></div>
                  <div><label className="label">Model</label><input className="input" value={s.ollama_model} onChange={(e) => set('ollama_model', e.target.value)} /></div>
                </>}
              </div>
              <div className="row" style={{ marginTop: 18 }}>
                <button className="btn btn-primary" onClick={save} disabled={saving}>{saving ? <Spinner /> : 'Save'}</button>
                <button className="btn btn-secondary" onClick={runTest} disabled={testing || s.provider === 'none'}>{testing ? <Spinner /> : 'Test connection'}</button>
                <div className="grow" />
                <span className={`badge ${s.ai?.available ? 'low' : 'neutral'}`}>{s.ai?.available ? `${s.ai.provider} · ready` : 'Offline mode'}</span>
              </div>
              {test && <div className={`callout ${test.ok ? '' : 'danger'}`} style={{ marginTop: 14 }}>
                <Icon name={test.ok ? 'check' : 'alert'} size={16} />{test.ok ? `Connected to ${test.provider} (${test.model}) in ${test.latency_ms} ms — “${test.message}”` : test.message}</div>}
            </div>
            <div className="card" data-reveal>
              <div className="h3" style={{ marginBottom: 4 }}>Semantic embeddings</div>
              <div className="small muted" style={{ marginBottom: 14 }}>Search always uses identifier-aware BM25. With an OpenAI key or Ollama, dense embeddings are fused in (reciprocal rank fusion). Re-analyse a project after changing this.</div>
              <Segmented value={s.embeddings} onChange={(v) => set('embeddings', v)} options={[{ value: 'auto', label: 'Auto' }, { value: 'openai', label: 'OpenAI' }, { value: 'ollama', label: 'Ollama' }, { value: 'none', label: 'Off' }]} />
            </div>
            </fieldset>
            {health && (
              <div className="card" data-reveal>
                <div className="h3" style={{ marginBottom: 12 }}>Analysis toolchain</div>
                <div className="grid g2">
                  {[['Java (javac AST)', health.tools.java, health.tools.java_path], ['Node.js', health.tools.node, health.tools.node_path],
                    ['TypeScript compiler', health.tools.typescript, 'backend/analyzers/js'], ['Git (history mining)', health.tools.git, '']].map(([l, ok, p]) => (
                    <div key={l as string} className="row"><span className={`dot ${ok ? 'low' : 'high'}`} /><div><div style={{ fontWeight: 600 }}>{l}</div><div className="tiny subtle">{ok ? p || 'available' : 'not found'}</div></div></div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
