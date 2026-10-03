import { useEffect, useMemo, useState } from 'react';
import { api } from '../lib/api';
import { nodeLayer, nodeName, useProject, useTwin } from '../lib/store';
import { useRouter } from '../lib/router';
import { LAYER_COLORS, modName, short } from '../lib/ui';
import Icon from '../components/Icon';
import CodeView from '../components/CodeView';
import { Empty, LayerTag, RiskBadge, Spinner } from '../components/Common';

interface TreeNode { name: string; path: string; children: Record<string, TreeNode>; file?: boolean }

export default function Explorer() {
  const twin = useTwin();
  const { meta, index } = useProject();
  const { loc, navigate } = useRouter();
  const pid = meta!.id;
  const [file, setFile] = useState<string | null>(loc.query.get('file') || twin.units[twin.summary.critical[0]]?.file || null);
  const [line, setLine] = useState<number | undefined>(Number(loc.query.get('line')) || undefined);
  const [endLine, setEndLine] = useState<number | undefined>(undefined);
  const [content, setContent] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState('');

  const tree = useMemo(() => {
    const root: TreeNode = { name: '', path: '', children: {} };
    for (const f of twin.files) {
      if (filter && !f.path.toLowerCase().includes(filter.toLowerCase())) continue;
      const parts = f.path.split('/');
      let cur = root;
      parts.forEach((p, i) => {
        const path = parts.slice(0, i + 1).join('/');
        cur.children[p] = cur.children[p] || { name: p, path, children: {}, file: i === parts.length - 1 };
        cur = cur.children[p];
      });
    }
    // compress single-child directory chains (com/shopverse/order -> com.shopverse.order)
    const compress = (n: TreeNode): TreeNode => {
      const kids = Object.values(n.children).map(compress);
      n.children = Object.fromEntries(kids.map((k) => [k.name, k]));
      if (!n.file && n.name && kids.length === 1 && !kids[0].file) {
        const k = kids[0];
        return { ...k, name: `${n.name}/${k.name}` };
      }
      return n;
    };
    return compress(root);
  }, [twin, filter]);

  useEffect(() => {
    if (!file) return;
    const parts = file.split('/');
    const s = new Set(open);
    parts.forEach((_, i) => s.add(parts.slice(0, i + 1).join('/')));
    setOpen(s);
    setContent(null);
    api.source(pid, file).then((r) => setContent(r.content)).catch(() => setContent('// unable to load file'));
    navigate(`/p/${pid}/code?file=${encodeURIComponent(file)}${line ? `&line=${line}` : ''}`, true);
  }, [file]);

  const fileRec = twin.files.find((f) => f.path === file);
  const units = Object.values(twin.units).filter((u) => u.file === file);
  const issues = twin.issues.filter((i) => i.file === file);
  const marks: Record<number, string> = {};
  units.forEach((u) => u.methods.forEach((m) => { if (m.complexity > 5) marks[m.line] = `${m.name}: complexity ${m.complexity}`; }));
  issues.forEach((i) => { marks[i.line] = i.title; });

  const isOpen = (p: string) => open.has(p) || !!filter;
  const renderNode = (n: TreeNode, depth: number): any => {
    const kids = Object.values(n.children).sort((a, b) => Number(!!a.file) - Number(!!b.file) || a.name.localeCompare(b.name));
    return kids.map((k) => {
      const f = k.file ? twin.files.find((x) => x.path === k.path) : null;
      const lvl = f?.debt?.level;
      return (
        <div key={k.path}>
          <div className={`tree-row ${k.path === file ? 'active' : ''}`} style={{ paddingLeft: 8 + depth * 14 }}
            onClick={() => { if (k.file) { setFile(k.path); setLine(undefined); setEndLine(undefined); } else { const s = new Set(open); s.has(k.path) ? s.delete(k.path) : s.add(k.path); setOpen(s); } }}>
            {k.file ? <Icon name="file" size={14} style={{ color: 'var(--text-3)' }} /> : <Icon name={isOpen(k.path) ? 'down' : 'chevron'} size={13} style={{ color: 'var(--text-3)' }} />}
            {!k.file && <Icon name="folder" size={14} style={{ color: 'var(--blue)' }} />}
            <span className="ellipsis grow">{k.name}</span>
            {lvl && lvl !== 'low' && <span className={`dot ${lvl}`} style={{ width: 7, height: 7 }} />}
          </div>
          {!k.file && isOpen(k.path) && renderNode(k, depth + 1)}
        </div>
      );
    });
  };

  return (
    <div className="page" style={{ maxWidth: 'none', paddingBottom: 20 }}>
      <div className="page-header" style={{ marginBottom: 16 }}>
        <div><div className="eyebrow">Where does this code sit in the whole system?</div><h1 className="h1">Code Explorer</h1></div>
      </div>
      <div className="code-layout">
        <div className="card pad-0" style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: 10, borderBottom: '1px solid var(--border)' }}>
            <input className="input" style={{ height: 34 }} placeholder="Filter files…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>
          <div className="tree grow">{renderNode(tree, 0)}</div>
        </div>
        <div className="card pad-0" style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {file ? (
            <>
              <div className="code-head">
                <Icon name="file" size={16} />
                <div className="grow" style={{ minWidth: 0 }}><div style={{ fontWeight: 600 }}>{short(file)}</div><div className="tiny subtle ellipsis">{file}</div></div>
                {fileRec?.sloc !== undefined && <span className="badge neutral">{fileRec.sloc} SLOC</span>}
                {fileRec?.mi !== undefined && <span className="badge neutral" title="Maintainability Index (Microsoft scale: 20–100 good, 10–19 moderate, <10 poor)" style={{ color: fileRec.mi >= 20 ? 'var(--green)' : fileRec.mi >= 10 ? 'var(--orange)' : 'var(--red)' }}>MI {fileRec.mi}</span>}
                {fileRec?.debt && <RiskBadge level={fileRec.debt.level} label={`Debt ${fileRec.debt.minutes} min`} />}
              </div>
              {content === null ? <div className="empty"><Spinner /></div> : <CodeView path={file} content={content} line={line} endLine={endLine} marks={marks} className="grow" />}
            </>
          ) : <Empty icon="code" title="Pick a file">Choose a file from the tree.</Empty>}
        </div>
        <div className="col code-side scroll-y" style={{ gap: 14 }}>
          {units.map((u) => (
            <div key={u.id} className="card" style={{ padding: 16 }}>
              <div className="row between"><LayerTag layer={u.layer} /><RiskBadge level={u.risk.level} /></div>
              <div className="h3" style={{ marginTop: 6 }}>{u.name}</div>
              <div className="tiny subtle">module {modName(u.module)} · {u.metrics.methods} methods · WMC {u.metrics.wmc}</div>
              <div className="row" style={{ gap: 6, marginTop: 10 }}>
                <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/p/${pid}/twin?node=${encodeURIComponent(u.id)}`)}><Icon name="twin" size={13} />Twin</button>
                <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/p/${pid}/impact?target=${encodeURIComponent(u.id)}`)}><Icon name="impact" size={13} />Impact</button>
              </div>
              <div className="eyebrow" style={{ margin: '14px 0 6px' }}>Methods</div>
              {u.methods.map((m) => (
                <div key={m.name + m.line} className="row between small clickable" style={{ padding: '3px 0' }} onClick={() => { setLine(m.line); setEndLine(m.endLine); }}>
                  <span className="mono ellipsis">{m.name}()</span>
                  <span className="num tiny" style={{ color: m.complexity > 10 ? 'var(--red)' : m.complexity > 5 ? 'var(--orange)' : 'var(--text-3)' }}>CC {m.complexity}</span>
                </div>
              ))}
              {[['Depends on', index.dependencies[u.id]], ['Used by', index.dependents[u.id]]].map(([t, ids]: any) => ids?.length ? (
                <div key={t}>
                  <div className="eyebrow" style={{ margin: '14px 0 6px' }}>{t}</div>
                  <div className="row wrap" style={{ gap: 4 }}>
                    {[...new Set(ids as string[])].slice(0, 16).map((id) => (
                      <span key={id} className="chip" style={{ height: 24, fontSize: 11.5 }} onClick={() => { const x = twin.units[id]; if (x) { setFile(x.file); setLine(x.line); } }}>
                        <span className="dot" style={{ background: LAYER_COLORS[nodeLayer(twin, id)] }} />{nodeName(twin, id)}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null)}
            </div>
          ))}
          {issues.length > 0 && (
            <div className="card" style={{ padding: 16 }}>
              <div className="h3" style={{ marginBottom: 8 }}>Findings in this file</div>
              {issues.map((i) => (
                <div key={i.id} className="clickable" style={{ padding: '6px 0' }} onClick={() => { setLine(i.line); setEndLine(i.line); }}>
                  <div className="row"><RiskBadge level={i.severity} /><b className="small">{i.title}</b></div>
                  <div className="tiny muted" style={{ marginTop: 3 }}>Line {i.line} · {i.detail}</div>
                </div>
              ))}
            </div>
          )}
          {fileRec?.debt_reasons && fileRec.debt_reasons.length > 0 && (
            <div className="card" style={{ padding: 16 }}>
              <div className="h3" style={{ marginBottom: 8 }}>Technical debt</div>
              {fileRec.debt_reasons.map((r) => <div key={r} className="small" style={{ padding: '2px 0' }}>• {r}</div>)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
