import { useEffect, useRef } from 'react';
import { gsap } from '../lib/anim';
import { useProject } from '../lib/store';
import { useRouter } from '../lib/router';
import Icon from '../components/Icon';
import { Spinner } from '../components/Common';

const STAGES = [
  ['Cloning repository', 'clone'],
  ['Scanning repository', 'scan'],
  ['Parsing', 'pars'],
  ['Building semantic model', 'semantic'],
  ['Constructing dependency graph', 'graph'],
  ['Mining git history', 'history'],
  ['Detecting duplicated code', 'duplic'],
  ['Running architecture, security and performance rules', 'rules'],
  ['Computing metrics and risk model', 'metric'],
  ['Scoring architecture health', 'health'],
  ['Indexing code for AI search', 'index'],
];

export default function Analyzing({ failed, message }: { failed?: boolean; message?: string }) {
  const { meta } = useProject();
  const { navigate } = useRouter();
  const card = useRef<HTMLDivElement>(null);
  const pct = Math.round((meta?.progress || 0) * 100);
  const stage = (meta?.stage || '').toLowerCase();
  const stages = STAGES.filter(([, k]) => k !== 'clone' || meta?.source?.type === 'git');
  let activeIdx = stages.findIndex(([, k]) => stage.includes(k));
  if (meta?.status === 'ready') activeIdx = stages.length;

  useEffect(() => {
    if (card.current) gsap.fromTo(card.current.querySelectorAll('[data-reveal]'), { y: 16, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, stagger: 0.05, ease: 'power3.out' });
  }, []);
  useEffect(() => {
    const el = card.current?.querySelector('.stage.active');
    if (el) gsap.fromTo(el, { scale: 0.97 }, { scale: 1, duration: 0.4, ease: 'back.out(2)' });
  }, [activeIdx]);

  return (
    <div className="analyzing">
      <div className="analyzing-card" ref={card}>
        <div data-reveal style={{ width: 72, height: 72, borderRadius: 22, margin: '0 auto 18px', display: 'grid', placeItems: 'center',
          background: failed ? 'var(--red-soft)' : 'var(--grad)', color: failed ? 'var(--red)' : '#fff', boxShadow: failed ? 'none' : '0 12px 34px rgba(94,92,230,.4)' }}>
          <Icon name={failed ? 'alert' : 'twin'} size={34} />
        </div>
        <h1 className="h1" data-reveal>{failed ? 'Analysis failed' : 'Building the Digital Twin'}</h1>
        <p className="lead" data-reveal style={{ fontSize: 17, marginTop: 8 }}>
          {failed ? message : `${meta?.name || 'Your project'} is being parsed, modelled and scored.`}
        </p>
        {!failed && (
          <>
            <div className="progress" data-reveal><i style={{ width: `${Math.max(4, pct)}%` }} /></div>
            <div className="row between small muted" style={{ marginTop: 8 }} data-reveal><span>{meta?.stage || 'Starting'}</span><span className="num">{pct}%</span></div>
            <div className="stage-list">
              {stages.map(([label], i) => (
                <div key={label} data-reveal className={`stage ${i < activeIdx ? 'done' : i === activeIdx ? 'active' : ''}`}>
                  <span className="tick">{i < activeIdx ? <Icon name="check" size={13} stroke={2.6} /> : i === activeIdx ? <Spinner size={12} /> : null}</span>
                  {i === activeIdx && meta?.stage ? meta.stage : label}
                </div>
              ))}
            </div>
          </>
        )}
        {failed && <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => navigate('/')}>Back to start</button>}
      </div>
    </div>
  );
}
