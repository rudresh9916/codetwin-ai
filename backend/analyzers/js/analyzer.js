#!/usr/bin/env node
/**
 * CodeTwin JavaScript / TypeScript analyzer.
 *
 * Uses the official TypeScript Compiler API to build a real AST for .js/.jsx/.ts/.tsx
 * files and prints JSON describing imports, exports, top-level members (functions,
 * classes, React components, hooks), cyclomatic complexity, HTTP API calls made by the
 * frontend (fetch / axios), server routes (Express / NestJS) and data models.
 *
 * Usage: node analyzer.js <file-with-list-of-paths>
 */
const fs = require('fs');
const path = require('path');

function loadTs() {
  const candidates = [
    process.env.CODETWIN_TS_PATH,
    path.join(__dirname, 'node_modules', 'typescript'),
    'typescript',
  ].filter(Boolean);
  for (const c of candidates) {
    try { return require(c); } catch (e) { /* try next */ }
  }
  console.error('typescript package not found. Run `npm install` in backend/analyzers/js');
  process.exit(2);
}
const ts = loadTs();
const HTTP_METHODS = new Set(['get', 'post', 'put', 'delete', 'patch', 'head', 'options']);

function lineOf(sf, pos) { return sf.getLineAndCharacterOfPosition(pos).line + 1; }

function hasDoc(node) {
  try { return (ts.getJSDocCommentsAndTags(node) || []).length > 0; } catch { return false; }
}

/** Convert a URL expression into a normalised path template like /orders/{param}. */
function urlFromExpr(expr) {
  if (!expr) return null;
  if (ts.isStringLiteral(expr) || ts.isNoSubstitutionTemplateLiteral(expr)) return expr.text;
  if (ts.isTemplateExpression(expr)) {
    let s = expr.head.text;
    for (const span of expr.templateSpans) s += '{param}' + span.literal.text;
    return s;
  }
  if (ts.isBinaryExpression(expr) && expr.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const l = urlFromExpr(expr.left);
    const r = urlFromExpr(expr.right);
    return (l === null ? '{param}' : l) + (r === null ? '{param}' : r);
  }
  return null;
}

function complexityOf(node) {
  let c = 1, maxNesting = 0;
  const calls = [];
  const idents = new Set();
  const jsx = new Set();
  let statements = 0;
  function visit(n, depth, loop) {
    let nextDepth = depth, inLoop = loop;
    switch (n.kind) {
      case ts.SyntaxKind.IfStatement:
      case ts.SyntaxKind.ConditionalExpression:
      case ts.SyntaxKind.CatchClause:
        c++; nextDepth = depth + 1; break;
      case ts.SyntaxKind.ForStatement:
      case ts.SyntaxKind.ForInStatement:
      case ts.SyntaxKind.ForOfStatement:
      case ts.SyntaxKind.WhileStatement:
      case ts.SyntaxKind.DoStatement:
        c++; nextDepth = depth + 1; inLoop = true; break;
      case ts.SyntaxKind.CaseClause:
        c++; break;
      case ts.SyntaxKind.BinaryExpression: {
        const k = n.operatorToken.kind;
        if (k === ts.SyntaxKind.AmpersandAmpersandToken || k === ts.SyntaxKind.BarBarToken || k === ts.SyntaxKind.QuestionQuestionToken) c++;
        break;
      }
      case ts.SyntaxKind.CallExpression: {
        const callee = n.expression;
        let name = null, root = null, receiver = null;
        if (ts.isIdentifier(callee)) { name = callee.text; root = callee.text; }
        else if (ts.isPropertyAccessExpression(callee)) {
          name = callee.name.text;
          receiver = callee.expression.getText().slice(0, 80);
          let cur = callee.expression;
          while (cur) {
            if (ts.isIdentifier(cur)) { root = cur.text; break; }
            if (cur.kind === ts.SyntaxKind.ThisKeyword) { root = 'this'; break; }
            if (ts.isPropertyAccessExpression(cur) || ts.isCallExpression(cur) || ts.isParenthesizedExpression(cur) || ts.isNonNullExpression(cur) || ts.isAwaitExpression(cur)) { cur = cur.expression; continue; }
            break;
          }
        }
        if (name) calls.push({ name, receiver, root, line: lineOf(n.getSourceFile(), n.getStart()), inLoop: loop, args: n.arguments.length });
        break;
      }
      case ts.SyntaxKind.Identifier:
        idents.add(n.text); break;
      case ts.SyntaxKind.JsxOpeningElement:
      case ts.SyntaxKind.JsxSelfClosingElement: {
        const t = n.tagName.getText();
        if (/^[A-Z]/.test(t)) jsx.add(t.split('.')[0]);
        break;
      }
    }
    if (ts.isStatement(n) && !ts.isBlock(n)) statements++;
    maxNesting = Math.max(maxNesting, nextDepth);
    ts.forEachChild(n, (ch) => visit(ch, nextDepth, inLoop));
  }
  ts.forEachChild(node, (ch) => visit(ch, 0, false));
  return { complexity: c, maxNesting, calls, idents: [...idents], jsx: [...jsx], statements };
}

function containsJsx(node) {
  let found = false;
  function v(n) {
    if (found) return;
    if (ts.isJsxElement(n) || ts.isJsxSelfClosingElement(n) || ts.isJsxFragment(n)) { found = true; return; }
    ts.forEachChild(n, v);
  }
  v(node);
  return found;
}

function decoratorsOf(node) {
  const out = [];
  const decs = (ts.canHaveDecorators && ts.canHaveDecorators(node)) ? (ts.getDecorators(node) || []) : (node.decorators || []);
  for (const d of decs) {
    const e = d.expression;
    if (ts.isCallExpression(e)) {
      const args = e.arguments.map((a) => (ts.isStringLiteral(a) ? a.text : a.getText().slice(0, 120)));
      out.push({ name: e.expression.getText(), args });
    } else out.push({ name: e.getText(), args: [] });
  }
  return out;
}

function isExported(node) {
  const mods = ts.canHaveModifiers && ts.canHaveModifiers(node) ? (ts.getModifiers(node) || []) : (node.modifiers || []);
  return mods.some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
}
function isDefault(node) {
  const mods = ts.canHaveModifiers && ts.canHaveModifiers(node) ? (ts.getModifiers(node) || []) : (node.modifiers || []);
  return mods.some((m) => m.kind === ts.SyntaxKind.DefaultKeyword);
}

function analyzeFile(file) {
  const text = fs.readFileSync(file, 'utf8');
  const ext = path.extname(file).toLowerCase();
  const kind = ext === '.tsx' ? ts.ScriptKind.TSX : ext === '.jsx' ? ts.ScriptKind.JSX : ext === '.ts' ? ts.ScriptKind.TS : ts.ScriptKind.JS;
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
  const result = {
    path: file, language: ext === '.ts' || ext === '.tsx' ? 'typescript' : 'javascript',
    imports: [], exports: [], defaultExport: null, members: [], apiCalls: [], routes: [],
    dbModels: [], httpClients: [], strings: [], parseErrors: (sf.parseDiagnostics || []).length,
  };
  const importedNames = {};

  function addMember(name, node, mkind, extra = {}) {
    const body = node;
    const m = complexityOf(body);
    const isComp = /^[A-Z]/.test(name) && (mkind === 'function' || mkind === 'const') && containsJsx(body);
    let finalKind = mkind === 'const' ? 'function' : mkind;
    if (isComp) finalKind = 'component';
    else if (/^use[A-Z0-9]/.test(name) && finalKind === 'function') finalKind = 'hook';
    result.members.push({
      name, kind: finalKind, line: lineOf(sf, node.getStart()), endLine: lineOf(sf, node.getEnd()),
      exported: extra.exported || false, doc: hasDoc(extra.docNode || node), complexity: m.complexity,
      maxNesting: m.maxNesting, statements: m.statements, calls: m.calls, idents: m.idents, jsx: m.jsx,
      params: extra.params || 0, decorators: extra.decorators || [], extends: extra.extends || [], implements: extra.implements || [],
      methods: extra.methods || [],
    });
  }

  function classInfo(node) {
    const ext = [], impl = [];
    for (const h of node.heritageClauses || []) {
      for (const t of h.types) (h.token === ts.SyntaxKind.ExtendsKeyword ? ext : impl).push(t.expression.getText());
    }
    const methods = [];
    for (const mem of node.members) {
      if ((ts.isMethodDeclaration(mem) || ts.isConstructorDeclaration(mem) || ts.isGetAccessor(mem) || ts.isSetAccessor(mem)) && mem.body) {
        const nm = ts.isConstructorDeclaration(mem) ? 'constructor' : mem.name.getText();
        const c = complexityOf(mem);
        methods.push({ name: nm, line: lineOf(sf, mem.getStart()), endLine: lineOf(sf, mem.getEnd()), complexity: c.complexity,
          maxNesting: c.maxNesting, statements: c.statements, calls: c.calls, doc: hasDoc(mem), decorators: decoratorsOf(mem),
          params: mem.parameters ? mem.parameters.length : 0 });
      }
    }
    return { extends: ext, implements: impl, methods, decorators: decoratorsOf(node) };
  }

  for (const st of sf.statements) {
    if (ts.isImportDeclaration(st)) {
      const source = st.moduleSpecifier.text;
      const names = [];
      const cl = st.importClause;
      if (cl) {
        if (cl.name) { names.push({ local: cl.name.text, imported: 'default' }); }
        if (cl.namedBindings) {
          if (ts.isNamespaceImport(cl.namedBindings)) names.push({ local: cl.namedBindings.name.text, imported: '*' });
          else for (const el of cl.namedBindings.elements) names.push({ local: el.name.text, imported: (el.propertyName || el.name).text });
        }
      }
      names.forEach((n) => { importedNames[n.local] = source; });
      result.imports.push({ source, names, line: lineOf(sf, st.getStart()), kind: 'import', typeOnly: !!(cl && cl.isTypeOnly) });
    } else if (ts.isExportDeclaration(st) && st.moduleSpecifier) {
      result.imports.push({ source: st.moduleSpecifier.text, names: [], line: lineOf(sf, st.getStart()), kind: 'export-from' });
    } else if (ts.isFunctionDeclaration(st) && st.name) {
      const exp = isExported(st);
      if (exp) result.exports.push(st.name.text);
      if (exp && isDefault(st)) result.defaultExport = st.name.text;
      addMember(st.name.text, st, 'function', { exported: exp, params: st.parameters.length });
    } else if (ts.isClassDeclaration(st) && st.name) {
      const exp = isExported(st);
      if (exp) result.exports.push(st.name.text);
      if (exp && isDefault(st)) result.defaultExport = st.name.text;
      addMember(st.name.text, st, 'class', { exported: exp, ...classInfo(st) });
    } else if (ts.isInterfaceDeclaration(st) || ts.isTypeAliasDeclaration(st) || ts.isEnumDeclaration(st)) {
      const exp = isExported(st);
      if (exp) result.exports.push(st.name.text);
      result.members.push({ name: st.name.text, kind: ts.isEnumDeclaration(st) ? 'enum' : 'type', line: lineOf(sf, st.getStart()),
        endLine: lineOf(sf, st.getEnd()), exported: exp, doc: hasDoc(st), complexity: 0, calls: [], idents: [], jsx: [], methods: [], statements: 0 });
    } else if (ts.isVariableStatement(st)) {
      const exp = isExported(st);
      for (const d of st.declarationList.declarations) {
        if (!ts.isIdentifier(d.name)) continue;
        const name = d.name.text;
        if (exp) result.exports.push(name);
        let init = d.initializer;
        while (init && (ts.isAsExpression(init) || ts.isParenthesizedExpression(init))) init = init.expression;
        // React.memo(...) / forwardRef(...) wrappers
        if (init && ts.isCallExpression(init) && init.arguments.length && (ts.isArrowFunction(init.arguments[0]) || ts.isFunctionExpression(init.arguments[0]))
          && /memo|forwardRef|observer/.test(init.expression.getText())) init = init.arguments[0];
        if (init && (ts.isArrowFunction(init) || ts.isFunctionExpression(init))) {
          addMember(name, init, 'const', { exported: exp, params: init.parameters.length, docNode: st });
        } else if (init && ts.isCallExpression(init)) {
          const callee = init.expression.getText();
          if (/^axios\.create$/.test(callee)) {
            let baseURL = null;
            const arg = init.arguments[0];
            if (arg && ts.isObjectLiteralExpression(arg)) {
              for (const p of arg.properties) if (ts.isPropertyAssignment(p) && p.name.getText() === 'baseURL') baseURL = urlFromExpr(p.initializer);
            }
            result.httpClients.push({ name, baseURL, line: lineOf(sf, d.getStart()) });
          }
          if (/(^|\.)model$/.test(callee) && init.arguments[0] && ts.isStringLiteral(init.arguments[0])) {
            result.dbModels.push({ name: init.arguments[0].text, kind: 'mongoose', line: lineOf(sf, d.getStart()) });
          }
          if (/\.define$/.test(callee) && init.arguments[0] && ts.isStringLiteral(init.arguments[0])) {
            result.dbModels.push({ name: init.arguments[0].text, kind: 'sequelize', line: lineOf(sf, d.getStart()) });
          }
          addMember(name, init, 'value', { exported: exp, docNode: st });
        } else if (init) {
          if (ts.isObjectLiteralExpression(init) || ts.isArrayLiteralExpression(init)) addMember(name, init, 'value', { exported: exp, docNode: st });
        }
      }
    } else if (ts.isExportAssignment(st)) {
      const e = st.expression;
      if (ts.isIdentifier(e)) result.defaultExport = e.text;
      else if (ts.isArrowFunction(e) || ts.isFunctionExpression(e)) { addMember('default', e, 'const', { exported: true }); result.defaultExport = 'default'; }
      else if (ts.isCallExpression(e)) {
        const c = complexityOf(e);
        result.members.push({ name: 'default', kind: 'value', line: lineOf(sf, e.getStart()), endLine: lineOf(sf, e.getEnd()), exported: true,
          doc: false, complexity: c.complexity, calls: c.calls, idents: c.idents, jsx: c.jsx, methods: [], statements: c.statements });
        result.defaultExport = 'default';
      }
    }
  }

  // Whole-file walk: requires, dynamic imports, HTTP calls, routes, strings
  function walk(n) {
    if (ts.isCallExpression(n)) {
      const callee = n.expression;
      const ln = lineOf(sf, n.getStart());
      if (ts.isIdentifier(callee) && callee.text === 'require' && n.arguments[0] && ts.isStringLiteral(n.arguments[0])) {
        result.imports.push({ source: n.arguments[0].text, names: [], line: ln, kind: 'require' });
      } else if (callee.kind === ts.SyntaxKind.ImportKeyword && n.arguments[0] && ts.isStringLiteral(n.arguments[0])) {
        result.imports.push({ source: n.arguments[0].text, names: [], line: ln, kind: 'dynamic' });
      } else if (ts.isIdentifier(callee) && callee.text === 'fetch') {
        const url = urlFromExpr(n.arguments[0]);
        let method = 'GET';
        const opts = n.arguments[1];
        if (opts && ts.isObjectLiteralExpression(opts)) {
          for (const p of opts.properties) if (ts.isPropertyAssignment(p) && p.name.getText() === 'method' && ts.isStringLiteral(p.initializer)) method = p.initializer.text.toUpperCase();
        }
        if (url) result.apiCalls.push({ method, url, line: ln, via: 'fetch', client: null });
      } else if (ts.isPropertyAccessExpression(callee) && HTTP_METHODS.has(callee.name.text)) {
        const obj = callee.expression.getText();
        const first = n.arguments[0];
        const url = urlFromExpr(first);
        const method = callee.name.text.toUpperCase();
        // Server route: app.get('/x', handler) / router.post('/x', ...)
        if (url && url.startsWith('/') && n.arguments.length >= 2 && /(app|router|server|api|routes?)$/i.test(obj)) {
          const h = n.arguments[n.arguments.length - 1];
          result.routes.push({ method, path: url, line: ln, handler: ts.isIdentifier(h) || ts.isPropertyAccessExpression(h) ? h.getText() : null, framework: 'express' });
        } else if (url !== null && (obj === 'axios' || importedNames[obj] || result.httpClients.some((c) => c.name === obj) || /client|api|http|request/i.test(obj))) {
          result.apiCalls.push({ method, url, line: ln, via: obj === 'axios' ? 'axios' : 'client', client: obj });
        }
      }
    }
    if ((ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) && n.text.length >= 2 && result.strings.length < 60) {
      result.strings.push(n.text.slice(0, 240));
    }
    ts.forEachChild(n, walk);
  }
  walk(sf);

  // NestJS controllers / TypeORM entities via decorators
  for (const m of result.members) {
    if (m.kind !== 'class') continue;
    const ctrl = (m.decorators || []).find((d) => d.name === 'Controller');
    if (ctrl) {
      const base = ctrl.args[0] || '';
      for (const mm of m.methods) {
        for (const d of mm.decorators || []) {
          if (HTTP_METHODS.has(d.name.toLowerCase())) {
            const sub = d.args[0] || '';
            const p = ('/' + [base, sub].filter(Boolean).join('/')).replace(/\/+/g, '/');
            result.routes.push({ method: d.name.toUpperCase(), path: p, line: mm.line, handler: m.name + '.' + mm.name, framework: 'nestjs' });
          }
        }
      }
    }
    if ((m.decorators || []).some((d) => d.name === 'Entity')) result.dbModels.push({ name: m.name, kind: 'typeorm', line: m.line });
  }
  return result;
}

function main() {
  const list = fs.readFileSync(process.argv[2], 'utf8').split(/\r?\n/).filter(Boolean);
  const out = [];
  for (const f of list) {
    try { out.push(analyzeFile(f)); } catch (e) { out.push({ path: f, error: String(e && e.message || e) }); }
  }
  process.stdout.write(JSON.stringify(out));
}
main();
