import { useEffect, useMemo, useRef, useState } from 'react';
import { hierarchy, treemap, treemapSquarify } from 'd3-hierarchy';
import { gsap } from '../lib/anim';

export interface TMItem { id: string; group: string; label: string; value: number; heat: number; tooltip?: string }

function heatColor(h: number) {
  // green -> yellow -> orange -> red
  const stops = [[48, 209, 88], [255, 214, 10], [255, 159, 10], [255, 69, 58]];
  const x = Math.max(0, Math.min(0.999, h)) * (stops.length - 1);
  const i = Math.floor(x), f = x - i;
  const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export default function Treemap({ items, height = 440, onClick }: { items: TMItem[]; height?: number; onClick?: (id: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(900);
  const [hover, setHover] = useState<TMItem | null>(null);
  useEffect(() => {
    const ro = new ResizeObserver(() => box.current && setW(box.current.clientWidth));
    if (box.current) { ro.observe(box.current); setW(box.current.clientWidth); }
    return () => ro.disconnect();
  }, []);
  const layout = useMemo(() => {
    const groups: Record<string, TMItem[]> = {};
    items.forEach((i) => { (groups[i.group] = groups[i.group] || []).push(i); });
    const root = hierarchy<any>({ children: Object.entries(groups).map(([g, ch]) => ({ name: g, children: ch })) })
      .sum((d: any) => (d.value ? Math.max(1, d.value) : 0)).sort((a, b) => (b.value || 0) - (a.value || 0));
    treemap<any>().tile(treemapSquarify).size([w, height]).paddingOuter(3).paddingTop(20).paddingInner(2).round(true)(root);
    return root;
  }, [items, w, height]);
  useEffect(() => {
    if (!box.current) return;
    const tw = gsap.fromTo(box.current.querySelectorAll('.tm-leaf'), { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.6, ease: 'power3.out', stagger: { amount: 0.6, from: 'random' } });
    return () => { tw.kill(); };
  }, [layout]);
  return (
    <div ref={box} style={{ position: 'relative', height, width: '100%' }} onMouseLeave={() => setHover(null)}>
      {(layout.children || []).map((g: any) => (
        <div key={g.data.name} style={{ position: 'absolute', left: g.x0, top: g.y0, width: g.x1 - g.x0, height: g.y1 - g.y0, borderRadius: 10, background: 'var(--surface-2)' }}>
          <div className="tiny ellipsis" style={{ padding: '3px 7px', fontWeight: 700, color: 'var(--text-2)' }}>{g.data.name}</div>
        </div>
      ))}
      {layout.leaves().map((l: any) => {
        const d: TMItem = l.data;
        const ww = l.x1 - l.x0, hh = l.y1 - l.y0;
        return (
          <div key={d.id} className="tm-leaf" onMouseEnter={() => setHover(d)} onClick={() => onClick?.(d.id)}
            style={{ position: 'absolute', left: l.x0, top: l.y0, width: ww, height: hh, background: heatColor(d.heat), borderRadius: 6, cursor: 'pointer',
              overflow: 'hidden', padding: ww > 50 && hh > 24 ? '4px 6px' : 0, color: d.heat > 0.55 ? '#fff' : '#1d1d1f', fontSize: 11, fontWeight: 600,
              boxShadow: hover?.id === d.id ? 'inset 0 0 0 2px var(--text)' : undefined, transformOrigin: 'center' }}>
            {ww > 50 && hh > 22 && <div className="ellipsis">{d.label}</div>}
          </div>
        );
      })}
      {hover && (
        <div className="floating small" style={{ position: 'absolute', right: 10, bottom: 10, padding: '10px 12px', maxWidth: 360, pointerEvents: 'none', zIndex: 3 }}>
          <b>{hover.label}</b><div className="tiny muted" style={{ whiteSpace: 'pre-line' }}>{hover.tooltip}</div>
        </div>
      )}
    </div>
  );
}
