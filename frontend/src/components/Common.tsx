import { ReactNode, useEffect, useMemo, useRef, useState } from 'react';
import Icon from './Icon';
import { useCountUp } from '../lib/anim';
import { LAYER_COLORS, LAYER_LABEL } from '../lib/ui';
import type { Twin } from '../lib/types';

export function StatCard({ label, value, icon, color, sub, decimals = 0, onClick }: {
  label: string; value: number; icon: string; color: string; sub?: string; decimals?: number; onClick?: () => void;
}) {
  const ref = useCountUp(value, decimals);
  return (
    <div className={`card ${onClick ? 'hover' : ''}`} data-reveal onClick={onClick}>
      <div className="stat-icon" style={{ background: `${color}1f`, color }}><Icon name={icon} size={18} /></div>
      <div className="stat">
        <div className="stat-value"><span ref={ref}>{value}</span></div>
        <div className="stat-label">{label}</div>
        {sub && <div className="tiny subtle">{sub}</div>}
      </div>
    </div>
  );
}

export function LayerTag({ layer, small }: { layer: string; small?: boolean }) {
  return (
    <span className="tag-layer" style={{ fontSize: small ? 11 : 12 }}>
      <span className="dot" style={{ background: LAYER_COLORS[layer] || '#8e8e93', width: small ? 7 : 8, height: small ? 7 : 8 }} />
      {LAYER_LABEL[layer] || layer}
    </span>
  );
}

export function RiskBadge({ level, label }: { level: string; label?: string }) {
  const l = (level || 'low').toLowerCase();
  return <span className={`badge ${l}`}>{label || l.charAt(0).toUpperCase() + l.slice(1)}</span>;
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void }) {
  return (
    <div className="segmented">
      {options.map((o) => (
        <button key={o.value} className={o.value === value ? 'active' : ''} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

export function Empty({ icon = 'sparkle', title, children }: { icon?: string; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div style={{ width: 54, height: 54, borderRadius: 16, margin: '0 auto 14px', display: 'grid', placeItems: 'center', background: 'var(--surface-2)', color: 'var(--text-2)' }}>
        <Icon name={icon} size={24} />
      </div>
      <div className="h3" style={{ marginBottom: 6 }}>{title}</div>
      <div className="muted">{children}</div>
    </div>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} />;
}

/** Searchable combobox over units / endpoints / tables / modules. */
export function NodePicker({ twin, value, onChange, kinds = ['unit', 'endpoint', 'table'], placeholder = 'Search a component, endpoint or table…' }: {
  twin: Twin; value: string | null; onChange: (id: string) => void; kinds?: ('unit' | 'endpoint' | 'table' | 'module')[]; placeholder?: string;
}) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState(0);
  const wrap = useRef<HTMLDivElement>(null);
  const all = useMemo(() => {
    const out: { id: string; label: string; sub: string; layer: string }[] = [];
    if (kinds.includes('unit')) for (const u of Object.values(twin.units)) if (!u.is_test) out.push({ id: u.id, label: u.name, sub: u.file, layer: u.layer });
    if (kinds.includes('endpoint')) for (const e of Object.values(twin.endpoints)) out.push({ id: e.id, label: `${e.method} ${e.path}`, sub: twin.units[e.unit]?.name || '', layer: 'endpoint' });
    if (kinds.includes('table')) for (const t of Object.values(twin.tables)) out.push({ id: t.id, label: t.name, sub: 'database table', layer: 'table' });
    if (kinds.includes('module')) for (const m of twin.modules) out.push({ id: m.id, label: m.name, sub: `${m.app || 'root'} · ${m.units.length} components`, layer: 'module' });
    return out;
  }, [twin, kinds.join()]);
  const current = all.find((a) => a.id === value);
  const list = useMemo(() => {
    const s = q.toLowerCase();
    return (s ? all.filter((a) => a.label.toLowerCase().includes(s) || a.sub.toLowerCase().includes(s)) : all).slice(0, 60);
  }, [q, all]);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  return (
    <div ref={wrap} style={{ position: 'relative', width: '100%' }}>
      <div style={{ position: 'relative' }}>
        <Icon name="search" size={16} style={{ position: 'absolute', left: 13, top: 12, color: 'var(--text-3)' }} />
        <input className="input" style={{ paddingLeft: 36 }} placeholder={current ? current.label : placeholder} value={open ? q : current ? current.label : ''}
          onFocus={() => { setOpen(true); setQ(''); setSel(0); }}
          onChange={(e) => { setQ(e.target.value); setSel(0); setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { setSel((s) => Math.min(list.length - 1, s + 1)); e.preventDefault(); }
            if (e.key === 'ArrowUp') { setSel((s) => Math.max(0, s - 1)); e.preventDefault(); }
            if (e.key === 'Enter' && list[sel]) { onChange(list[sel].id); setOpen(false); (e.target as HTMLInputElement).blur(); }
            if (e.key === 'Escape') setOpen(false);
          }} />
      </div>
      {open && (
        <div className="card" style={{ position: 'absolute', top: 46, left: 0, right: 0, zIndex: 50, padding: 6, maxHeight: 340, overflow: 'auto', boxShadow: 'var(--shadow-lg)' }}>
          {list.length === 0 && <div className="small muted" style={{ padding: 10 }}>No matches</div>}
          {list.map((a, i) => (
            <div key={a.id} className="list-item" style={{ padding: '7px 10px', background: i === sel ? 'var(--surface-2)' : undefined }}
              onMouseEnter={() => setSel(i)} onMouseDown={(e) => { e.preventDefault(); onChange(a.id); setOpen(false); }}>
              <span className="dot" style={{ background: LAYER_COLORS[a.layer] || '#8e8e93' }} />
              <div className="grow">
                <div style={{ fontWeight: 600, fontSize: 13 }} className="ellipsis">{a.label}</div>
                <div className="tiny subtle ellipsis">{a.sub}</div>
              </div>
              <span className="tiny subtle">{LAYER_LABEL[a.layer] || a.layer}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Toast({ msg, onDone }: { msg: string; onDone: () => void }) {
  useEffect(() => { const t = setTimeout(onDone, 2600); return () => clearTimeout(t); }, [msg]);
  return <div className="toast">{msg}</div>;
}

export function SectionTitle({ icon, title, sub, right }: { icon?: string; title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="card-title">
      <div>
        <div className="h3">{icon && <Icon name={icon} size={17} style={{ color: 'var(--text-2)' }} />}{title}</div>
        {sub && <div className="card-sub">{sub}</div>}
      </div>
      {right}
    </div>
  );
}
