import { useEffect, useMemo, useRef } from 'react';
import hljs from 'highlight.js/lib/common';
import { langOf } from '../lib/ui';

/** Syntax-highlighted source with line numbers, a highlighted range and gutter marks. */
export default function CodeView({ path, content, line, endLine, marks, className }: {
  path: string; content: string; line?: number; endLine?: number; marks?: Record<number, string>; className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const lines = useMemo(() => {
    const lang = langOf(path);
    let html: string;
    try {
      html = hljs.getLanguage(lang) ? hljs.highlight(content, { language: lang, ignoreIllegals: true }).value : hljs.highlightAuto(content).value;
    } catch {
      html = content.replace(/&/g, '&amp;').replace(/</g, '&lt;');
    }
    // split highlighted HTML into lines while keeping spans balanced
    const out: string[] = [];
    let open: string[] = [];
    for (const ln of html.split('\n')) {
      let line = open.join('') + ln;
      const tags = ln.match(/<span[^>]*>|<\/span>/g) || [];
      for (const t of tags) { if (t.startsWith('</')) open.pop(); else open.push(t); }
      line += '</span>'.repeat(open.length);
      out.push(line);
    }
    return out;
  }, [path, content]);

  useEffect(() => {
    if (!line || !ref.current) return;
    const row = ref.current.querySelector(`tr[data-ln="${line}"]`) as HTMLElement | null;
    if (row) {
      const box = ref.current;
      box.scrollTo({ top: Math.max(0, row.offsetTop - box.clientHeight / 3), behavior: 'smooth' });
    }
  }, [line, content]);

  const end = endLine || line;
  return (
    <div ref={ref} className={`code-view ${className || ''}`}>
      <table>
        <tbody>
          {lines.map((l, i) => {
            const n = i + 1;
            const hl = line && n >= line && n <= (end || line);
            return (
              <tr key={n} data-ln={n} className={`${hl ? 'hl' : ''} ${marks?.[n] ? 'mark' : ''}`} title={marks?.[n]}>
                <td className="ln">{n}</td>
                <td className="src" dangerouslySetInnerHTML={{ __html: l || ' ' }} />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
