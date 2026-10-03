import { useEffect, useRef } from 'react';
import { gsap, useCountUp } from '../lib/anim';
import { scoreColor } from '../lib/ui';

/** Apple-Watch-like ring for a 0..100 score. */
export function ScoreRing({ value, size = 160, stroke = 14, label, sub, color }: { value: number; size?: number; stroke?: number; label?: string; sub?: string; color?: string }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const arc = useRef<SVGCircleElement>(null);
  const num = useCountUp(value);
  const col = color || scoreColor(value);
  useEffect(() => {
    if (!arc.current) return;
    const target = c * (1 - value / 100);
    arc.current.style.strokeDashoffset = String(target);
    const tw = gsap.fromTo(arc.current, { strokeDashoffset: c }, { strokeDashoffset: target, duration: 1.4, ease: 'power3.out' });
    return () => { tw.kill(); };
  }, [value, c]);
  return (
    <div style={{ position: 'relative', width: size, height: size, flex: 'none' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--surface-2)" strokeWidth={stroke} fill="none" />
        <circle ref={arc} cx={size / 2} cy={size / 2} r={r} stroke={col} strokeWidth={stroke} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center' }}>
        <div>
          <div className="num" style={{ fontSize: size * 0.27, fontWeight: 700, letterSpacing: '-0.04em', lineHeight: 1 }}><span ref={num}>{value}</span></div>
          {label && <div className="small muted" style={{ marginTop: 4, fontWeight: 600 }}>{label}</div>}
          {sub && <div className="tiny subtle">{sub}</div>}
        </div>
      </div>
    </div>
  );
}

export function Radar({ data, size = 300 }: { data: { label: string; value: number }[]; size?: number }) {
  const ref = useRef<SVGPolygonElement>(null);
  const cx = size / 2, cy = size / 2, R = size / 2 - 58;
  const n = data.length;
  const pt = (i: number, v: number) => {
    const a = (Math.PI * 2 * i) / n - Math.PI / 2;
    return [cx + Math.cos(a) * R * v, cy + Math.sin(a) * R * v];
  };
  const poly = data.map((d, i) => pt(i, d.value / 100).join(',')).join(' ');
  useEffect(() => {
    if (!ref.current) return;
    const tw = gsap.fromTo(ref.current, { scale: 0.2, opacity: 0, transformOrigin: `${cx}px ${cy}px` }, { scale: 1, opacity: 1, duration: 1.1, ease: 'expo.out' });
    return () => { tw.kill(); };
  }, [poly]);
  return (
    <svg width="100%" viewBox={`-50 -6 ${size + 100} ${size + 12}`} className="svg-chart" style={{ maxWidth: size + 100 }}>
      <defs>
        <linearGradient id="radarFill" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0a84ff" stopOpacity="0.45" />
          <stop offset="1" stopColor="#bf5af2" stopOpacity="0.35" />
        </linearGradient>
      </defs>
      {[0.25, 0.5, 0.75, 1].map((k) => (
        <polygon key={k} points={data.map((_, i) => pt(i, k).join(',')).join(' ')} fill="none" stroke="var(--border-strong)" strokeWidth={1} />
      ))}
      {data.map((_, i) => { const [x, y] = pt(i, 1); return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--border)" />; })}
      <polygon ref={ref} points={poly} fill="url(#radarFill)" stroke="#5e5ce6" strokeWidth={2} strokeLinejoin="round" />
      {data.map((d, i) => { const [x, y] = pt(i, d.value / 100); return <circle key={i} cx={x} cy={y} r={3.5} fill="#5e5ce6" />; })}
      {data.map((d, i) => {
        const [x, y] = pt(i, 1.2);
        return (
          <text key={i} x={x} y={y} textAnchor={Math.abs(x - cx) < 10 ? 'middle' : x > cx ? 'start' : 'end'} dominantBaseline="middle" style={{ fontSize: 13, fontWeight: 600 }}>
            {d.label} <tspan style={{ fill: 'var(--text)' }}>{d.value}</tspan>
          </text>
        );
      })}
    </svg>
  );
}

export function Bar({ value, max = 100, color }: { value: number; max?: number; color?: string }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const tw = gsap.fromTo(ref.current, { scaleX: 0 }, { scaleX: 1, duration: 1, ease: 'power3.out' });
    return () => { tw.kill(); };
  }, [value]);
  return <div className="bar"><i ref={ref as any} style={{ width: `${Math.max(2, Math.min(100, (value / (max || 1)) * 100))}%`, background: color || scoreColor(value) }} /></div>;
}

export function Sparkbars({ data, height = 120, color = 'var(--blue)', labels }: { data: number[]; height?: number; color?: string; labels?: string[] }) {
  const ref = useRef<SVGGElement>(null);
  const max = Math.max(1, ...data);
  const w = 100 / Math.max(1, data.length);
  useEffect(() => {
    if (!ref.current) return;
    const tw = gsap.fromTo(ref.current.children, { scaleY: 0, transformOrigin: 'bottom' }, { scaleY: 1, duration: 0.8, ease: 'power3.out', stagger: 0.008 });
    return () => { tw.kill(); };
  }, [data.length]);
  return (
    <svg width="100%" height={height} viewBox={`0 0 100 ${height}`} preserveAspectRatio="none">
      <g ref={ref}>
        {data.map((v, i) => (
          <rect key={i} x={i * w + w * 0.15} width={w * 0.7} y={height - (v / max) * (height - 4)} height={(v / max) * (height - 4)} rx={Math.min(1.2, w * 0.3)} fill={color}>
            {labels && <title>{labels[i]}: {v}</title>}
          </rect>
        ))}
      </g>
    </svg>
  );
}

export function LineChart({ series, labels, height = 180 }: { series: { name: string; color: string; values: number[] }[]; labels: string[]; height?: number }) {
  const W = 600, H = height, pad = 30;
  const n = labels.length;
  const x = (i: number) => pad + (n <= 1 ? 0 : (i * (W - pad * 2)) / (n - 1));
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="svg-chart">
      {[0, 0.5, 1].map((k) => <line key={k} x1={pad} x2={W - pad} y1={pad / 2 + (H - pad * 1.5) * k} y2={pad / 2 + (H - pad * 1.5) * k} stroke="var(--border)" />)}
      {series.map((s) => {
        const max = Math.max(1, ...s.values), min = Math.min(0, ...s.values);
        const y = (v: number) => pad / 2 + (H - pad * 1.5) * (1 - (v - min) / (max - min || 1));
        const d = s.values.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join(' ');
        return (
          <g key={s.name}>
            <path d={d} fill="none" stroke={s.color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
            {s.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={4} fill="var(--surface)" stroke={s.color} strokeWidth={2}><title>{s.name}: {v}</title></circle>)}
          </g>
        );
      })}
      {labels.map((l, i) => <text key={i} x={x(i)} y={H - 4} textAnchor="middle">{l}</text>)}
    </svg>
  );
}

/** Scatter plot used for hotspot (churn × complexity) and the main-sequence chart. */
export function Scatter({ points, xLabel, yLabel, height = 260, xMax, yMax, diagonal, onClick }: {
  points: { x: number; y: number; r?: number; color?: string; label: string; id?: string }[]; xLabel: string; yLabel: string; height?: number;
  xMax?: number; yMax?: number; diagonal?: boolean; onClick?: (id: string) => void;
}) {
  const W = 560, H = height, pl = 44, pb = 34, pt = 12, pr = 16;
  const mx = xMax ?? Math.max(1, ...points.map((p) => p.x)) * 1.1;
  const my = yMax ?? Math.max(1, ...points.map((p) => p.y)) * 1.1;
  const sx = (v: number) => pl + (v / mx) * (W - pl - pr);
  const sy = (v: number) => H - pb - (v / my) * (H - pb - pt);
  const g = useRef<SVGGElement>(null);
  useEffect(() => {
    if (!g.current) return;
    const tw = gsap.fromTo(g.current.querySelectorAll('circle'), { attr: { r: 0 } }, { attr: { r: (i: number, el: any) => el.dataset.r }, duration: 0.8, ease: 'back.out(2)', stagger: 0.02 });
    return () => { tw.kill(); };
  }, [points.length]);
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="svg-chart">
      <line x1={pl} y1={H - pb} x2={W - pr} y2={H - pb} stroke="var(--border-strong)" />
      <line x1={pl} y1={pt} x2={pl} y2={H - pb} stroke="var(--border-strong)" />
      {diagonal && <line x1={sx(0)} y1={sy(my)} x2={sx(mx)} y2={sy(0)} stroke="var(--green)" strokeDasharray="5 5" opacity={0.7} />}
      <text x={(W + pl) / 2} y={H - 6} textAnchor="middle">{xLabel}</text>
      <text x={12} y={(H - pb) / 2} textAnchor="middle" transform={`rotate(-90 12 ${(H - pb) / 2})`}>{yLabel}</text>
      <g ref={g}>
        {points.map((p, i) => (
          <g key={i} style={{ cursor: onClick ? 'pointer' : 'default' }} onClick={() => p.id && onClick?.(p.id)}>
            <circle cx={sx(p.x)} cy={sy(p.y)} r={p.r ?? 6} data-r={p.r ?? 6} fill={p.color || 'var(--blue)'} fillOpacity={0.75} stroke="var(--surface)" strokeWidth={1.5}>
              <title>{p.label} ({p.x}, {p.y})</title>
            </circle>
            {(p.r ?? 6) >= 9 && <text x={sx(p.x) + (p.r ?? 6) + 4} y={sy(p.y) + 4} style={{ fontSize: 11, fontWeight: 600, fill: 'var(--text)' }}>{p.label}</text>}
          </g>
        ))}
      </g>
    </svg>
  );
}
