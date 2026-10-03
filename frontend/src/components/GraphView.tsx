import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import cytoscape from 'cytoscape';
import fcose from 'cytoscape-fcose';
import { gsap } from '../lib/anim';

let registered = false;
if (!registered) { try { cytoscape.use(fcose as any); } catch { /* already */ } registered = true; }

export interface GNode { id: string; label: string; color: string; size?: number; parent?: string; kind?: string; shape?: string; border?: string; title?: string; isParent?: boolean }
export interface GEdge { id: string; source: string; target: string; type?: string; weight?: number; color?: string; label?: string }
export interface GraphHandle { fit: () => void; zoom: (f: number) => void; focus: (id: string) => void; png: () => string | undefined }

function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
}

const GraphView = forwardRef<GraphHandle, {
  nodes: GNode[]; edges: GEdge[]; selected?: string | null; onSelect?: (id: string | null) => void; layout?: 'fcose' | 'concentric' | 'breadthfirst' | 'grid';
  highlight?: Record<string, number> | null; concentricKey?: Record<string, number>; animate?: boolean; height?: number | string; minimal?: boolean;
  roots?: string[];
}>(function GraphView({ nodes, edges, selected, onSelect, layout = 'fcose', highlight, concentricKey, animate = true, minimal, roots }, ref) {
  const box = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useImperativeHandle(ref, () => ({
    fit: () => cyRef.current?.animate({ fit: { eles: cyRef.current.elements(), padding: 40 } } as any, { duration: 500, easing: 'ease-out-cubic' } as any),
    zoom: (f: number) => { const cy = cyRef.current; if (cy) cy.animate({ zoom: cy.zoom() * f, center: { eles: cy.elements(':selected').length ? cy.elements(':selected') : cy.elements() } } as any, { duration: 250 } as any); },
    focus: (id: string) => {
      const cy = cyRef.current; if (!cy) return;
      const n = cy.getElementById(id); if (!n.length) return;
      cy.animate({ center: { eles: n }, zoom: Math.max(cy.zoom(), 1.1) } as any, { duration: 500, easing: 'ease-out-cubic' } as any);
      n.select();
    },
    png: () => cyRef.current?.png({ full: true, scale: 2, bg: cssVar('--bg-2') }),
  }));

  // build / rebuild graph
  useEffect(() => {
    if (!box.current) return;
    const text = cssVar('--text');
    const text2 = cssVar('--text-2');
    const surface = cssVar('--surface');
    const border = cssVar('--border-strong');
    const cy = cytoscape({
      container: box.current,
      wheelSensitivity: 0.25,
      minZoom: 0.08,
      maxZoom: 3.5,
      boxSelectionEnabled: false,
      elements: [
        ...nodes.map((n) => ({ data: { ...n, size: n.size ?? 26 }, classes: [n.isParent ? 'parent' : '', n.kind || ''].join(' ') })),
        ...edges.map((e) => ({ data: { ...e, weight: e.weight ?? 1 }, classes: e.type || '' })),
      ],
      style: [
        { selector: 'node', style: {
          'background-color': 'data(color)', label: 'data(label)', color: text, 'font-size': minimal ? 12 : 11, 'font-weight': 600,
          'font-family': '-apple-system, BlinkMacSystemFont, Inter, sans-serif', 'text-valign': 'bottom', 'text-margin-y': 5,
          width: 'data(size)', height: 'data(size)', 'border-width': 2.5, 'border-color': surface, 'text-outline-color': surface,
          'text-outline-width': 2.5, 'transition-property': 'opacity, border-color, border-width, background-color', 'transition-duration': 250 as any,
          'overlay-opacity': 0, 'min-zoomed-font-size': 3,
        } as any },
        { selector: 'node.endpoint', style: { shape: 'round-tag', 'font-size': 9, color: text2 } as any },
        { selector: 'node.table', style: { shape: 'barrel', width: 30, height: 34 } as any },
        { selector: 'node.interface', style: { shape: 'diamond' } as any },
        { selector: 'node.parent', style: {
          'background-color': 'data(color)', 'background-opacity': 0.06, 'border-width': 1.5, 'border-style': 'dashed', 'border-color': 'data(color)',
          'border-opacity': 0.55, shape: 'round-rectangle', 'text-valign': 'top', 'text-halign': 'center', 'text-margin-y': -6, 'font-size': 13,
          'font-weight': 700, color: text2, padding: '18px', 'corner-radius': 18,
        } as any },
        { selector: 'edge', style: {
          width: 'mapData(weight, 0, 8, 1.1, 4)', 'line-color': border, 'target-arrow-color': border, 'target-arrow-shape': 'triangle',
          'arrow-scale': 0.8, 'curve-style': 'bezier', opacity: 0.85, 'transition-property': 'opacity, line-color', 'transition-duration': 250 as any,
        } as any },
        { selector: 'edge.http', style: { 'line-style': 'dashed', 'line-color': '#ff375f', 'target-arrow-color': '#ff375f', opacity: 0.7 } as any },
        { selector: 'edge.implements, edge.inherits', style: { 'line-style': 'dotted', 'target-arrow-shape': 'triangle-backcurve' } as any },
        { selector: 'edge.handles', style: { 'line-color': '#0a84ff', 'target-arrow-color': '#0a84ff', opacity: 0.5 } as any },
        { selector: 'edge.maps, edge.persists', style: { 'line-color': '#30d158', 'target-arrow-color': '#30d158', opacity: 0.6 } as any },
        { selector: 'edge[color]', style: { 'line-color': 'data(color)', 'target-arrow-color': 'data(color)' } as any },
        { selector: 'edge[label]', style: { label: 'data(label)', 'font-size': 10, color: text2, 'text-background-color': surface, 'text-background-opacity': 1, 'text-background-padding': '2px' } as any },
        { selector: '.faded', style: { opacity: 0.1 } as any },
        { selector: 'node:selected', style: { 'border-color': '#0a84ff', 'border-width': 4 } as any },
        { selector: 'node.focus', style: { 'border-color': '#0a84ff', 'border-width': 4, 'z-index': 99 } as any },
        { selector: 'edge.focus', style: { 'line-color': '#0a84ff', 'target-arrow-color': '#0a84ff', opacity: 1, width: 2.4, 'z-index': 98 } as any },
        { selector: 'edge.focus-in', style: { 'line-color': '#bf5af2', 'target-arrow-color': '#bf5af2', opacity: 1, width: 2.4 } as any },
        { selector: 'node.impact-0', style: { 'background-color': '#ff3b30', 'border-color': '#ff3b30', 'border-width': 6, 'border-opacity': 0.35 } as any },
        { selector: 'node.impact-1', style: { 'border-color': '#ff9f0a', 'border-width': 5 } as any },
        { selector: 'node.impact-2', style: { 'border-color': '#ffd60a', 'border-width': 4 } as any },
        { selector: 'node.impact-3', style: { 'border-color': '#64d2ff', 'border-width': 3 } as any },
        { selector: 'edge.impact', style: { 'line-color': '#ff9f0a', 'target-arrow-color': '#ff9f0a', opacity: 1, width: 2.6 } as any },
      ],
      layout: { name: 'preset' },
    });
    cyRef.current = cy;

    const runLayout = () => {
      let opts: any;
      if (layout === 'concentric' && concentricKey) {
        // radial "blast radius": distance d from the changed node -> ring d, nodes spread evenly on each ring
        const rings: Record<number, string[]> = {};
        cy.nodes().forEach((n: any) => { const d = concentricKey[n.id()] ?? 4; (rings[d] = rings[d] || []).push(n.id()); });
        const pos: Record<string, { x: number; y: number }> = {};
        Object.entries(rings).forEach(([dk, ids]) => {
          const d = Number(dk);
          ids.forEach((id, k) => {
            const a = (2 * Math.PI * k) / ids.length + d * 0.7;
            const r = d === 0 ? 0 : 75 * Math.pow(d, 0.72) + (ids.length > 8 ? 30 : 0);
            pos[id] = { x: Math.cos(a) * r, y: Math.sin(a) * r };
          });
        });
        opts = { name: 'preset', positions: (n: any) => pos[n.id()] || { x: 0, y: 0 }, fit: true, padding: 30, animate, animationDuration: 700 };
      } else if (layout === 'concentric') {
        opts = { name: 'concentric', concentric: (n: any) => n.degree(), levelWidth: () => 1, minNodeSpacing: 34, animate, animationDuration: 700, padding: 40 };
      } else if (layout === 'breadthfirst') {
        opts = { name: 'breadthfirst', directed: false, circle: !!roots, roots: roots && roots.length ? roots.map((r) => '#' + CSS.escape(r)).join(',') : undefined,
          spacingFactor: roots ? 0.9 : 1.2, animate, animationDuration: 700, padding: 30 };
      } else if (layout === 'grid') {
        opts = { name: 'grid', animate, padding: 30 };
      } else {
        opts = { name: 'fcose', quality: 'proof', animate, animationDuration: 900, animationEasing: 'ease-out-cubic', randomize: true,
          nodeRepulsion: () => 9000, idealEdgeLength: () => 90, edgeElasticity: () => 0.35, nestingFactor: 0.6, gravity: 0.3,
          gravityCompound: 1.4, numIter: 2500, tile: true, packComponents: true, nodeSeparation: 90, padding: 40, uniformNodeDimensions: false };
      }
      try { cy.layout(opts).run(); } catch { cy.layout({ name: 'cose', animate: false } as any).run(); }
    };
    runLayout();

    cy.on('tap', 'node', (e) => { if (!e.target.isParent()) onSelectRef.current?.(e.target.id()); });
    cy.on('tap', (e) => { if (e.target === cy) onSelectRef.current?.(null); });
    cy.on('mouseover', 'node', (e) => { box.current!.style.cursor = 'pointer'; e.target.addClass('hover'); });
    cy.on('mouseout', 'node', () => { box.current!.style.cursor = ''; });

    if (box.current) gsap.fromTo(box.current, { opacity: 0 }, { opacity: 1, duration: 0.6, ease: 'power2.out' });

    const onTheme = () => {
      const s = cssVar('--surface');
      cy.style().selector('node').style({ color: cssVar('--text'), 'border-color': s, 'text-outline-color': s } as any).update();
    };
    window.addEventListener('ct-theme', onTheme);
    return () => { window.removeEventListener('ct-theme', onTheme); cy.destroy(); cyRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, layout]);

  // selection highlighting
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || highlight) return;
    cy.elements().removeClass('faded focus focus-in');
    if (!selected) return;
    const n = cy.getElementById(selected);
    if (!n.length) return;
    const out = n.outgoers('edge');
    const inc = n.incomers('edge');
    const keep = n.union(out).union(inc).union(out.targets()).union(inc.sources()).union(n.ancestors());
    keep.ancestors?.();
    cy.elements().not(keep).not(cy.nodes(':parent')).addClass('faded');
    n.addClass('focus');
    out.addClass('focus');
    inc.addClass('focus-in');
  }, [selected, nodes, edges, highlight]);

  // impact highlighting
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().removeClass('impact-0 impact-1 impact-2 impact-3 impact faded');
    if (!highlight) return;
    cy.elements().removeClass('focus focus-in');
    cy.$(':selected').unselect();
    cy.nodes().forEach((n) => {
      if (n.isParent()) return;
      const d = highlight[n.id()];
      if (d === undefined) n.addClass('faded');
      else n.addClass(`impact-${Math.min(3, d)}`);
    });
    cy.edges().forEach((e) => {
      const a = highlight[e.source().id()], b = highlight[e.target().id()];
      if (a !== undefined && b !== undefined && a === b + 1) e.addClass('impact');
      else e.addClass('faded');
    });
    // ripple: pulse the affected nodes outward by distance
    const byD: Record<number, any[]> = {};
    Object.entries(highlight).forEach(([id, d]) => { (byD[d] = byD[d] || []).push(id); });
    Object.keys(byD).map(Number).sort((a, b) => a - b).forEach((d) => {
      setTimeout(() => {
        byD[d].forEach((id) => {
          const n = cy.getElementById(id);
          if (!n.length) return;
          const w = n.width();
          n.animate({ style: { width: w * 1.45, height: w * 1.45 } } as any, { duration: 260, complete: () => n.animate({ style: { width: w, height: w } } as any, { duration: 380 }) } as any);
        });
      }, 260 + d * 300);
    });
  }, [highlight, nodes, edges]);

  return <div ref={box} className="graph-canvas" />;
});

export default GraphView;
