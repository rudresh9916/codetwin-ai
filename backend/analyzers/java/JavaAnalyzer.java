import com.sun.source.doctree.DocCommentTree;
import com.sun.source.tree.*;
import com.sun.source.util.*;

import javax.tools.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/**
 * CodeTwin Java analyzer.
 *
 * Parses Java source files with the JDK's own compiler front-end (com.sun.source / javac)
 * and prints a JSON description of every compilation unit: package, imports, types,
 * fields, methods, cyclomatic complexity, method invocations and referenced types.
 *
 * Usage: java JavaAnalyzer.java <file-with-list-of-paths>
 * Only the parse phase runs, so no classpath / dependencies are needed.
 */
public class JavaAnalyzer {

    public static void main(String[] args) throws Exception {
        List<String> paths = Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8);
        paths.removeIf(String::isBlank);
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        PrintStream out = new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8);
        out.print("[");
        boolean first = true;
        // Parse in batches to keep memory bounded on large repositories.
        int batch = 200;
        for (int i = 0; i < paths.size(); i += batch) {
            List<String> chunk = paths.subList(i, Math.min(paths.size(), i + batch));
            DiagnosticCollector<JavaFileObject> diags = new DiagnosticCollector<>();
            StandardJavaFileManager fm = compiler.getStandardFileManager(diags, Locale.ROOT, StandardCharsets.UTF_8);
            List<File> files = new ArrayList<>();
            for (String p : chunk) files.add(new File(p));
            Iterable<? extends JavaFileObject> objs = fm.getJavaFileObjectsFromFiles(files);
            JavacTask task = (JavacTask) compiler.getTask(null, fm, diags, List.of("-proc:none", "-Xlint:none"), null, objs);
            Iterable<? extends CompilationUnitTree> units;
            try {
                units = task.parse();
            } catch (Throwable t) {
                continue;
            }
            DocTrees docTrees = DocTrees.instance(task);
            SourcePositions pos = docTrees.getSourcePositions();
            for (CompilationUnitTree cu : units) {
                try {
                    String json = new UnitVisitor(cu, docTrees, pos).toJson();
                    if (!first) out.print(",");
                    out.print(json);
                    first = false;
                } catch (Throwable t) {
                    // skip unparsable unit
                }
            }
            fm.close();
        }
        out.print("]");
        out.flush();
    }

    // ------------------------------------------------------------------ JSON helpers
    static String q(String s) {
        if (s == null) return "null";
        StringBuilder sb = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                    else sb.append(c);
            }
        }
        return sb.append('"').toString();
    }

    static String arr(Collection<String> items) {
        StringBuilder sb = new StringBuilder("[");
        boolean f = true;
        for (String s : items) {
            if (!f) sb.append(',');
            sb.append(s);
            f = false;
        }
        return sb.append(']').toString();
    }

    static String strArr(Collection<String> items) {
        List<String> qs = new ArrayList<>();
        for (String s : items) qs.add(q(s));
        return arr(qs);
    }

    static String clip(String s, int n) {
        if (s == null) return null;
        s = s.replaceAll("\\s+", " ");
        return s.length() > n ? s.substring(0, n) + "…" : s;
    }

    // ------------------------------------------------------------------ Visitor
    static class UnitVisitor {
        final CompilationUnitTree cu;
        final DocTrees docTrees;
        final SourcePositions pos;
        final LineMap lines;
        final List<String> typeJson = new ArrayList<>();

        UnitVisitor(CompilationUnitTree cu, DocTrees docTrees, SourcePositions pos) {
            this.cu = cu;
            this.docTrees = docTrees;
            this.pos = pos;
            this.lines = cu.getLineMap();
        }

        long line(Tree t) {
            long p = pos.getStartPosition(cu, t);
            return p < 0 ? 0 : lines.getLineNumber(p);
        }

        long endLine(Tree t) {
            long p = pos.getEndPosition(cu, t);
            return p < 0 ? line(t) : lines.getLineNumber(p);
        }

        boolean hasDoc(Tree t) {
            try {
                DocCommentTree d = docTrees.getDocCommentTree(TreePath.getPath(cu, t));
                return d != null;
            } catch (Throwable e) {
                return false;
            }
        }

        String annotations(List<? extends AnnotationTree> anns) {
            List<String> out = new ArrayList<>();
            for (AnnotationTree a : anns) {
                String name = a.getAnnotationType().toString();
                if (name.contains(".")) name = name.substring(name.lastIndexOf('.') + 1);
                List<String> kv = new ArrayList<>();
                for (ExpressionTree arg : a.getArguments()) {
                    String key = "value";
                    ExpressionTree val = arg;
                    if (arg instanceof AssignmentTree as) {
                        key = as.getVariable().toString();
                        val = as.getExpression();
                    }
                    String v = val.toString();
                    if (val instanceof LiteralTree lt && lt.getValue() != null) v = lt.getValue().toString();
                    else if (val instanceof NewArrayTree na) {
                        List<String> parts = new ArrayList<>();
                        for (ExpressionTree e : na.getInitializers()) {
                            if (e instanceof LiteralTree l2 && l2.getValue() != null) parts.add(l2.getValue().toString());
                            else parts.add(e.toString());
                        }
                        v = String.join(",", parts);
                    }
                    kv.add(q(key) + ":" + q(clip(v, 200)));
                }
                out.add("{\"name\":" + q(name) + ",\"args\":{" + String.join(",", kv) + "}}");
            }
            return arr(out);
        }

        String modifiers(ModifiersTree m) {
            List<String> mods = new ArrayList<>();
            for (javax.lang.model.element.Modifier mod : m.getFlags()) mods.add(mod.toString());
            return strArr(mods);
        }

        String toJson() {
            String pkg = cu.getPackageName() == null ? "" : cu.getPackageName().toString();
            List<String> imports = new ArrayList<>();
            for (ImportTree it : cu.getImports()) {
                String name = it.getQualifiedIdentifier().toString();
                imports.add("{\"name\":" + q(name) + ",\"static\":" + it.isStatic() + ",\"wildcard\":" + name.endsWith(".*") + ",\"line\":" + line(it) + "}");
            }
            for (Tree t : cu.getTypeDecls()) {
                if (t instanceof ClassTree ct) visitClass(ct, null);
            }
            String path;
            try {
                path = Path.of(cu.getSourceFile().toUri()).toAbsolutePath().toString();  // OS-native (Windows-safe)
            } catch (Exception e) {
                path = cu.getSourceFile().getName();
            }
            return "{\"path\":" + q(path) + ",\"package\":" + q(pkg)
                    + ",\"imports\":" + arr(imports) + ",\"types\":" + arr(typeJson) + "}";
        }

        void visitClass(ClassTree ct, String outer) {
            String simple = ct.getSimpleName().toString();
            String name = outer == null ? simple : outer + "." + simple;
            String kind = switch (ct.getKind()) {
                case INTERFACE -> "interface";
                case ENUM -> "enum";
                case ANNOTATION_TYPE -> "annotation";
                case RECORD -> "record";
                default -> "class";
            };
            List<String> ext = new ArrayList<>();
            if (ct.getExtendsClause() != null) ext.add(q(ct.getExtendsClause().toString()));
            List<String> impl = new ArrayList<>();
            for (Tree i : ct.getImplementsClause()) impl.add(q(i.toString()));
            if (ct.getKind() == Tree.Kind.INTERFACE) { // interfaces "extend" via implements clause in javac
                ext.addAll(impl);
                impl.clear();
            }
            List<String> fields = new ArrayList<>();
            List<String> methods = new ArrayList<>();
            Set<String> typeRefs = new TreeSet<>();
            List<String> recordComponents = new ArrayList<>();

            for (Tree member : ct.getMembers()) {
                if (member instanceof VariableTree vt) {
                    String type = vt.getType() == null ? "var" : vt.getType().toString();
                    // record components appear as private final fields too
                    fields.add("{\"name\":" + q(vt.getName().toString()) + ",\"type\":" + q(type)
                            + ",\"annotations\":" + annotations(vt.getModifiers().getAnnotations())
                            + ",\"modifiers\":" + modifiers(vt.getModifiers())
                            + ",\"init\":" + q(vt.getInitializer() == null ? null : clip(vt.getInitializer().toString(), 160))
                            + ",\"line\":" + line(vt) + "}");
                    collectTypes(vt, typeRefs);
                } else if (member instanceof MethodTree mt) {
                    methods.add(visitMethod(mt, simple, typeRefs));
                } else if (member instanceof ClassTree inner) {
                    visitClass(inner, name);
                } else if (member instanceof BlockTree bt) {
                    collectTypes(bt, typeRefs);
                }
            }
            if (ct.getExtendsClause() != null) collectTypes(ct.getExtendsClause(), typeRefs);
            for (Tree i : ct.getImplementsClause()) collectTypes(i, typeRefs);
            for (AnnotationTree a : ct.getModifiers().getAnnotations()) collectTypes(a, typeRefs);
            typeRefs.remove(simple);

            typeJson.add("{\"name\":" + q(name) + ",\"simpleName\":" + q(simple) + ",\"kind\":" + q(kind)
                    + ",\"line\":" + line(ct) + ",\"endLine\":" + endLine(ct)
                    + ",\"modifiers\":" + modifiers(ct.getModifiers())
                    + ",\"annotations\":" + annotations(ct.getModifiers().getAnnotations())
                    + ",\"extends\":" + arr(ext) + ",\"implements\":" + arr(impl)
                    + ",\"doc\":" + hasDoc(ct) + ",\"outer\":" + q(outer)
                    + ",\"fields\":" + arr(fields) + ",\"methods\":" + arr(methods)
                    + ",\"typeRefs\":" + strArr(typeRefs) + "}");
        }

        String visitMethod(MethodTree mt, String className, Set<String> typeRefs) {
            String name = mt.getName().toString();
            boolean ctor = name.equals("<init>");
            if (ctor) name = className;
            List<String> params = new ArrayList<>();
            for (VariableTree p : mt.getParameters()) {
                params.add("{\"name\":" + q(p.getName().toString()) + ",\"type\":" + q(p.getType() == null ? "" : p.getType().toString())
                        + ",\"annotations\":" + annotations(p.getModifiers().getAnnotations()) + "}");
            }
            MethodScanner ms = new MethodScanner();
            if (mt.getBody() != null) ms.scan(mt.getBody(), null);
            collectTypes(mt, typeRefs);
            long start = line(mt), end = endLine(mt);
            return "{\"name\":" + q(name) + ",\"constructor\":" + ctor
                    + ",\"line\":" + start + ",\"endLine\":" + end
                    + ",\"returnType\":" + q(mt.getReturnType() == null ? null : mt.getReturnType().toString())
                    + ",\"params\":" + arr(params)
                    + ",\"annotations\":" + annotations(mt.getModifiers().getAnnotations())
                    + ",\"modifiers\":" + modifiers(mt.getModifiers())
                    + ",\"abstract\":" + (mt.getBody() == null)
                    + ",\"doc\":" + hasDoc(mt)
                    + ",\"complexity\":" + ms.complexity + ",\"maxNesting\":" + ms.maxNesting
                    + ",\"statements\":" + ms.statements
                    + ",\"calls\":" + arr(ms.calls)
                    + ",\"instantiations\":" + strArr(ms.newTypes)
                    + ",\"strings\":" + strArr(ms.strings) + "}";
        }

        void collectTypes(Tree t, Set<String> refs) {
            new TreeScanner<Void, Void>() {
                @Override
                public Void visitIdentifier(IdentifierTree node, Void v) {
                    String n = node.getName().toString();
                    if (!n.isEmpty() && Character.isUpperCase(n.charAt(0)) && !n.equals(n.toUpperCase())) refs.add(n);
                    else if (n.length() > 1 && Character.isUpperCase(n.charAt(0)) && n.chars().anyMatch(Character::isLowerCase)) refs.add(n);
                    return super.visitIdentifier(node, v);
                }
            }.scan(t, null);
        }

        class MethodScanner extends TreeScanner<Void, Void> {
            int complexity = 1;
            int loopDepth = 0;
            int nesting = 0;
            int maxNesting = 0;
            int statements = 0;
            final List<String> calls = new ArrayList<>();
            final Set<String> newTypes = new TreeSet<>();
            final Set<String> strings = new LinkedHashSet<>();

            void enter() { nesting++; maxNesting = Math.max(maxNesting, nesting); }

            @Override public Void visitIf(IfTree n, Void v) { complexity++; statements++; enter(); super.visitIf(n, v); nesting--; return null; }
            @Override public Void visitForLoop(ForLoopTree n, Void v) { complexity++; statements++; loopDepth++; enter(); super.visitForLoop(n, v); nesting--; loopDepth--; return null; }
            @Override public Void visitEnhancedForLoop(EnhancedForLoopTree n, Void v) { complexity++; statements++; loopDepth++; enter(); super.visitEnhancedForLoop(n, v); nesting--; loopDepth--; return null; }
            @Override public Void visitWhileLoop(WhileLoopTree n, Void v) { complexity++; statements++; loopDepth++; enter(); super.visitWhileLoop(n, v); nesting--; loopDepth--; return null; }
            @Override public Void visitDoWhileLoop(DoWhileLoopTree n, Void v) { complexity++; statements++; loopDepth++; enter(); super.visitDoWhileLoop(n, v); nesting--; loopDepth--; return null; }
            @Override public Void visitCase(CaseTree n, Void v) { if (!n.getExpressions().isEmpty()) complexity++; return super.visitCase(n, v); }
            @Override public Void visitCatch(CatchTree n, Void v) { complexity++; enter(); super.visitCatch(n, v); nesting--; return null; }
            @Override public Void visitConditionalExpression(ConditionalExpressionTree n, Void v) { complexity++; return super.visitConditionalExpression(n, v); }
            @Override public Void visitSwitch(SwitchTree n, Void v) { statements++; enter(); super.visitSwitch(n, v); nesting--; return null; }
            @Override public Void visitTry(TryTree n, Void v) { statements++; return super.visitTry(n, v); }
            @Override public Void visitReturn(ReturnTree n, Void v) { statements++; return super.visitReturn(n, v); }
            @Override public Void visitThrow(ThrowTree n, Void v) { statements++; return super.visitThrow(n, v); }
            @Override public Void visitExpressionStatement(ExpressionStatementTree n, Void v) { statements++; return super.visitExpressionStatement(n, v); }
            @Override public Void visitVariable(VariableTree n, Void v) { statements++; return super.visitVariable(n, v); }

            @Override
            public Void visitBinary(BinaryTree n, Void v) {
                if (n.getKind() == Tree.Kind.CONDITIONAL_AND || n.getKind() == Tree.Kind.CONDITIONAL_OR) complexity++;
                return super.visitBinary(n, v);
            }

            @Override
            public Void visitLiteral(LiteralTree n, Void v) {
                if (n.getValue() instanceof String s && s.length() >= 2 && strings.size() < 40) strings.add(clip(s, 240));
                return super.visitLiteral(n, v);
            }

            @Override
            public Void visitNewClass(NewClassTree n, Void v) {
                String t = n.getIdentifier().toString();
                int lt = t.indexOf('<');
                if (lt > 0) t = t.substring(0, lt);
                if (t.contains(".")) t = t.substring(t.lastIndexOf('.') + 1);
                newTypes.add(t);
                return super.visitNewClass(n, v);
            }

            @Override
            public Void visitMethodInvocation(MethodInvocationTree n, Void v) {
                ExpressionTree sel = n.getMethodSelect();
                String name;
                String receiver = null;
                String root = null;
                if (sel instanceof MemberSelectTree ms) {
                    name = ms.getIdentifier().toString();
                    ExpressionTree e = ms.getExpression();
                    receiver = clip(e.toString(), 80);
                    // find the root identifier of the receiver chain: this.a.b().c -> a
                    ExpressionTree cur = e;
                    while (true) {
                        if (cur instanceof MemberSelectTree m2) {
                            if (m2.getExpression() instanceof IdentifierTree id && id.getName().contentEquals("this")) {
                                root = m2.getIdentifier().toString();
                                break;
                            }
                            cur = m2.getExpression();
                        } else if (cur instanceof MethodInvocationTree mi) {
                            cur = mi.getMethodSelect();
                        } else if (cur instanceof IdentifierTree id) {
                            root = id.getName().toString();
                            break;
                        } else if (cur instanceof ParenthesizedTree pt) {
                            cur = pt.getExpression();
                        } else if (cur instanceof NewClassTree nc) {
                            root = "new " + nc.getIdentifier().toString();
                            break;
                        } else {
                            break;
                        }
                    }
                } else {
                    name = sel.toString();
                    root = "this";
                }
                calls.add("{\"name\":" + q(name) + ",\"receiver\":" + q(receiver) + ",\"root\":" + q(root)
                        + ",\"line\":" + line(n) + ",\"inLoop\":" + (loopDepth > 0) + ",\"args\":" + n.getArguments().size() + "}");
                return super.visitMethodInvocation(n, v);
            }

            @Override
            public Void visitLambdaExpression(LambdaExpressionTree n, Void v) {
                return super.visitLambdaExpression(n, v);
            }
        }
    }
}
