import { useEffect, useMemo, useRef } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/common';
import { getTheme } from '../lib/ui';

let mermaidPromise: Promise<any> | null = null;
let mermaidTheme = '';
async function getMermaid() {
  if (!mermaidPromise) mermaidPromise = import('mermaid').then((m) => m.default);
  const mm = await mermaidPromise;
  const theme = getTheme() === 'dark' ? 'dark' : 'neutral';
  if (theme !== mermaidTheme) {
    mermaidTheme = theme;
    mm.initialize({ startOnLoad: false, theme, securityLevel: 'strict', fontFamily: '-apple-system, BlinkMacSystemFont, Inter, sans-serif',
      flowchart: { curve: 'basis', htmlLabels: true }, sequence: { mirrorActors: false } });
  }
  return mm;
}
let seq = 0;

export default function Markdown({ text, onCite, className }: { text: string; onCite?: (n: number) => void; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const html = useMemo(() => {
    const raw = marked.parse(text || '', { gfm: true, breaks: false }) as string;
    let clean = DOMPurify.sanitize(raw);
    if (onCite) clean = clean.replace(/\[(\d{1,2})\](?![^<]*<\/code>)/g, '<span class="cite" data-cite="$1">$1</span>');
    return clean;
  }, [text, !!onCite]);
  // React 19 re-applies innerHTML whenever the prop object identity changes, so keep it stable
  const inner = useMemo(() => ({ __html: html }), [html]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.querySelectorAll('pre code').forEach((block) => {
      const b = block as HTMLElement;
      if (b.classList.contains('language-mermaid')) {
        const src = b.textContent || '';
        const holder = document.createElement('div');
        holder.className = 'mermaid-box';
        holder.textContent = 'Rendering diagram…';
        b.parentElement!.replaceWith(holder);
        getMermaid().catch((e) => { console.warn('mermaid load failed', e?.message || e); throw e; }).then(async (mm) => {
          try {
            const { svg } = await mm.render(`mmd-${++seq}`, src);
            holder.innerHTML = svg;
          } catch (e: any) {
            console.warn('mermaid render failed', e?.message || e);
            holder.innerHTML = '';
            const pre = document.createElement('pre');
            pre.textContent = src;
            holder.appendChild(pre);
          }
        });
      } else if (!b.dataset.hl) {
        try { hljs.highlightElement(b); } catch { /* ignore */ }
        b.dataset.hl = '1';
      }
    });
  }, [html]);

  return (
    <div ref={ref} className={`md ${className || ''}`} dangerouslySetInnerHTML={inner}
      onClick={(e) => { const t = e.target as HTMLElement; if (t.dataset.cite && onCite) onCite(Number(t.dataset.cite)); }} />
  );
}
