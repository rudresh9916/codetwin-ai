export type Level = 'high' | 'medium' | 'low';

export interface Method {
  name: string; line: number; endLine: number; loc: number; complexity: number; maxNesting?: number; doc?: boolean;
  public?: boolean; constructor?: boolean; params?: string[]; returnType?: string | null; annotations?: string[];
  resolvedCalls?: { target: string; method: string; line: number; inLoop?: boolean }[]; kind?: string;
}

export interface Unit {
  id: string; name: string; fqn: string; kind: string; layer: string; language: string; file: string; line: number; endLine: number;
  loc: number; module: string; app: string; package: string; annotations: string[]; doc: boolean; extends: string[]; implements: string[];
  fields: { name: string; type: string; annotations: string[] }[]; methods: Method[]; is_test: boolean; abstract?: boolean;
  metrics: {
    methods: number; wmc: number; logic: number; max_cc: number; avg_cc: number; loc: number; fan_in: number; fan_out: number; instability: number;
    dependents_transitive: number; dependencies_transitive: number; pagerank: number; betweenness: number; doc_coverage: number; tested: boolean;
    churn: number; recent_churn: number; fixes: number; authors: number; issues: number; criticality: number; domains: Record<string, string[]>;
  };
  risk: { score: number; level: Level; reasons: string[]; factors: Record<string, number> };
  god_class?: boolean; apiCalls?: { method: string; full: string; line: number; endpoint?: string }[]; exports?: string[];
  members?: { name: string; kind: string; line: number; exported: boolean }[];
}

export interface Endpoint {
  id: string; method: string; path: string; unit: string; handler: string; file: string; line: number; framework: string;
  params: { name: string; type: string; in: string }[]; consumers: string[]; tested: boolean; unused: boolean; returns?: string | null;
}

export interface Table { id: string; name: string; entity: string; columns: { name: string; type: string; id?: boolean; relation?: string }[]; source: string; relations: any[] }
export interface Edge { source: string; target: string; type: string; types: string[]; details: string[]; weight: number }
export interface Issue { id: string; category: string; severity: string; title: string; detail: string; file: string; line: number; unit: string | null; principle?: string | null; rule: string }
export interface Module { id: string; name: string; app: string; units: string[]; files: number; loc: number; layers: Record<string, number>; language: string; tests: number; risk: number; wmc: number; metrics: any }
export interface FileRec {
  path: string; ext: string; language: string; loc: number; sloc: number; comments: number; blank: number; is_test: boolean; analyzed: boolean;
  complexity?: number; max_cc?: number; mi?: number; churn?: number; fixes?: number; authors?: string[]; duplicate_lines?: number; units?: string[];
  debt?: { minutes: number; by_category: Record<string, number>; ratio: number; rating: string; score: number; level: Level }; debt_reasons?: string[];
}
export interface HealthDim { score: number; grade: string; summary: string; metrics: Record<string, any> }
export interface Refactoring {
  id: string; type: string; title: string; unit: string | null; file: string; line: number; priority: Level; principle: string; problem: string;
  suggestion: string; proposed: { name: string; responsibility: string; methods: string[]; existing?: boolean; from_line?: number }[];
  notes: string[]; effort_hours: number; benefit: string;
}

export interface Twin {
  version: number; name: string; generated_at: string; duration_s: number; warnings: string[]; project_id: string;
  summary: {
    name: string; architecture: string; languages: Record<string, number>; language_loc: Record<string, number>; frameworks: { name: string; category: string }[];
    databases: string[]; counts: Record<string, number>; layers: Record<string, number>; critical: string[]; high_risk: string[]; entry_points: string[];
    unused_endpoints: string[]; possibly_dead: string[]; health: number; debt_level: string; debt_hours: number;
  };
  apps: { dir: string; name: string; kind: string }[];
  modules: Module[]; units: Record<string, Unit>; endpoints: Record<string, Endpoint>; tables: Record<string, Table>; edges: Edge[];
  cycles: string[][]; clones: any[]; issues: Issue[]; refactorings: Refactoring[];
  health: { overall: number; grade: string; dimensions: Record<string, HealthDim>; weights: Record<string, number> };
  debt: { minutes: number; hours: number; days: number; ratio: number; rating: string; level: string; by_category: Record<string, number>; files: any[] };
  history: any; files: FileRec[]; libraries: Record<string, string[]>; configs: string[]; docs: string[];
}

export interface ProjectMeta {
  id: string; name: string; source: any; status: string; stage: string; progress: number; created_at: string; updated_at: string;
  error: string | null; summary?: any; warnings?: string[]; analyzed_at?: string;
}
