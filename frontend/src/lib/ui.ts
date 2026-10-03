export const LAYER_COLORS: Record<string, string> = {
  controller: '#0a84ff', service: '#bf5af2', repository: '#ff9f0a', entity: '#30d158', dto: '#98989d', config: '#8e8e93',
  component: '#40c8e0', page: '#5e5ce6', api: '#ff375f', hook: '#64d2ff', context: '#da8fff', store: '#da8fff', util: '#ac8e68',
  interface: '#c7a26b', enum: '#a2845e', exception: '#8e8e93', model: '#66d4cf', route: '#0a84ff', entry: '#ffd60a', module: '#8e8e93',
  types: '#aeaeb2', test: '#d1d1d6', endpoint: '#ff6b6b', table: '#32d74b',
};
export const LAYER_LABEL: Record<string, string> = {
  controller: 'Controller', service: 'Service', repository: 'Repository', entity: 'Entity', dto: 'DTO', config: 'Config', component: 'Component',
  page: 'Page', api: 'API client', hook: 'Hook', context: 'Context', store: 'Store', util: 'Utility', interface: 'Interface', enum: 'Enum',
  exception: 'Exception', model: 'Model', route: 'Route', entry: 'Entry', module: 'Module', types: 'Types', test: 'Test', endpoint: 'Endpoint',
  table: 'DB table',
};
export const RISK_COLORS = { high: '#ff453a', medium: '#ff9f0a', low: '#30d158' } as Record<string, string>;
export const DIM_LABEL: Record<string, string> = {
  modularity: 'Modularity', coupling: 'Coupling', complexity: 'Complexity', maintainability: 'Maintainability',
  documentation: 'Documentation', testability: 'Testability', security: 'Security', performance: 'Performance',
};
export const DIM_HINT: Record<string, string> = {
  modularity: 'Newman modularity Q of the package partition, dependency cycles, distance from the main sequence',
  coupling: 'Average fan-out and components with 7+ direct dependencies',
  complexity: 'Share of methods with cyclomatic complexity above 10/20',
  maintainability: 'LOC-weighted Maintainability Index, god classes, duplication',
  documentation: 'Javadoc / JSDoc coverage of public API, README',
  testability: 'Components with tests, test-to-code ratio',
  security: 'OWASP-mapped static rules (secrets, injection, XSS, CORS, CSRF…)',
  performance: 'N+1 queries, unbounded queries, stateful singletons',
};

export function scoreColor(s: number) {
  return s >= 80 ? 'var(--green)' : s >= 60 ? 'var(--blue)' : s >= 45 ? 'var(--orange)' : 'var(--red)';
}
export function levelOf(score: number): 'high' | 'medium' | 'low' { return score >= 0.6 ? 'high' : score >= 0.4 ? 'medium' : 'low'; }
export const fmt = (n: number | undefined, d = 0) => (n ?? 0).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
export const short = (path: string) => path.split('/').pop() || path;
export const modName = (id: string) => id.split('::').pop() || id;
export function timeAgo(iso: string) {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return 'just now';
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return `${Math.floor(d / 86400)} d ago`;
}
export function langOf(path: string) {
  if (path.endsWith('.java')) return 'java';
  if (/\.(ts|tsx)$/.test(path)) return 'typescript';
  if (/\.(js|jsx|mjs|cjs)$/.test(path)) return 'javascript';
  if (/\.(ya?ml)$/.test(path)) return 'yaml';
  if (path.endsWith('.json')) return 'json';
  if (path.endsWith('.xml')) return 'xml';
  if (path.endsWith('.sql')) return 'sql';
  if (path.endsWith('.md')) return 'markdown';
  if (path.endsWith('.properties')) return 'properties';
  return 'plaintext';
}
export function setTheme(t: 'light' | 'dark') {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('ct-theme', t); } catch { /* ignore */ }
  window.dispatchEvent(new Event('ct-theme'));
}
export function getTheme(): 'light' | 'dark' {
  return (document.documentElement.dataset.theme as any) || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}
