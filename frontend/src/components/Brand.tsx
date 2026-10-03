import { useEffect, useState } from 'react';
import { getTheme, setTheme } from '../lib/ui';
import Icon from './Icon';

export function ThemeToggle() {
  const [t, setT] = useState(getTheme());
  useEffect(() => { const h = () => setT(getTheme()); window.addEventListener('ct-theme', h); return () => window.removeEventListener('ct-theme', h); }, []);
  return (
    <button className="btn btn-secondary btn-icon btn-sm" title="Toggle appearance" onClick={() => setTheme(t === 'dark' ? 'light' : 'dark')}>
      <Icon name={t === 'dark' ? 'sun' : 'moon'} size={15} />
    </button>
  );
}

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <div className="brand-logo" style={{ width: size, height: size, borderRadius: size * 0.3 }}>
      <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth={2.2} strokeLinecap="round">
        <circle cx="7" cy="8" r="2.4" fill="#fff" /><circle cx="17" cy="8" r="2.4" fill="#fff" /><circle cx="12" cy="17" r="2.6" fill="#fff" />
        <path d="M7 8l5 9 5-9" />
      </svg>
    </div>
  );
}

