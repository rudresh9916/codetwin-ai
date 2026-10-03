import { useEffect, useLayoutEffect, useRef, RefObject } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Staggered fade-up for every [data-reveal] element inside the container (runs on mount / when deps change). */
export function useReveal(ref: RefObject<HTMLElement | null>, deps: any[] = []) {
  useLayoutEffect(() => {
    if (!ref.current || reduced()) return;
    const ctx = gsap.context(() => {
      const els = ref.current!.querySelectorAll('[data-reveal]');
      if (els.length) {
        gsap.fromTo(els, { y: 18, opacity: 0, scale: 0.985 },
          { y: 0, opacity: 1, scale: 1, duration: 0.7, ease: 'power3.out', stagger: 0.045, clearProps: 'transform' });
      }
    }, ref);
    return () => ctx.revert();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/** Animate a number from 0 to `value`, writing into the element's textContent. */
export function useCountUp(value: number, decimals = 0, duration = 1.2) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fmt = (v: number) => v.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    if (reduced()) { el.textContent = fmt(value); return; }
    const obj = { v: 0 };
    const tw = gsap.to(obj, { v: value, duration, ease: 'power2.out', onUpdate: () => { el.textContent = fmt(obj.v); } });
    el.textContent = fmt(value);
    tw.progress(0);
    return () => { tw.kill(); el.textContent = fmt(value); };
  }, [value, decimals, duration]);
  return ref;
}

/** Scroll-triggered reveal for landing sections. */
export function useScrollReveal(ref: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    if (!ref.current || reduced()) return;
    const ctx = gsap.context(() => {
      ref.current!.querySelectorAll('[data-scroll]').forEach((el, i) => {
        gsap.fromTo(el, { y: 40, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.9, ease: 'power3.out', delay: (i % 3) * 0.08,
          scrollTrigger: { trigger: el as Element, start: 'top 88%' },
        });
      });
    }, ref);
    return () => ctx.revert();
  }, []);
}

export function pulse(el: Element | null) {
  if (!el || reduced()) return;
  gsap.fromTo(el, { scale: 0.96 }, { scale: 1, duration: 0.5, ease: 'elastic.out(1, 0.5)' });
}

export { gsap };
