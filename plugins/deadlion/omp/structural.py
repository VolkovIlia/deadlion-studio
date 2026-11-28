"""Collect existing Suckless measures for a refactoring baseline or checkpoint."""
import ast
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path


def load_budget():
    path = Path(__file__).resolve().parents[1] / "skills/suckless-code/scripts/dl-budget"
    loader = importlib.machinery.SourceFileLoader("dl_budget", str(path))
    spec = importlib.util.spec_from_loader("dl_budget", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def ast_identity(node):
    return ast.dump(node, include_attributes=False)


def symbols(body, parents=()):
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            qualified = (*parents, node.name)
            if not isinstance(node, ast.ClassDef):
                yield node, ".".join(qualified)
            yield from symbols(node.body, qualified)
        else:
            yield from symbols(list(ast.iter_child_nodes(node)), parents)


def fingerprint(text):
    return hashlib.sha256(text.encode()).hexdigest()


def python_functions(size, lines):
    try:
        tree = ast.parse("".join(lines), type_comments=True)
    except SyntaxError:
        return [], "invalid Python syntax"
    records = []
    for node, name in symbols(tree.body):
        signature = ast_identity(node.args) + repr([ast_identity(d) for d in node.decorator_list])
        body = [ast_identity(item) for item in node.body]
        records.append(dict(name=name, key=name + ":" + fingerprint(signature),
                            fingerprint=fingerprint(repr([type(node).__name__, signature, body, ast_identity(node.returns) if node.returns else None])),
                            lines=size.count_function_lines(node, lines)))
    return records, None


def function_sizes(size, path, lines):
    if size.is_python(path):
        return python_functions(size, lines)
    try:
        import lizard
    except ImportError:
        return [], "Lizard unavailable"
    if not lizard.get_reader_for(str(path)):
        return [], "No Lizard reader for this language"
    result = lizard.analyze_file.analyze_source_code(str(path), "".join(lines))
    return [dict(name=item.long_name, key=item.long_name, lines=item.nloc,
                 fingerprint=fingerprint("".join(lines[item.start_line - 1:item.end_line])))
            for item in result.function_list], None


def structures(root, names):
    budget = load_budget()
    size = budget.dl
    files, projects = {}, {}
    components = {"."}
    for name in names:
        path = Path(name)
        if path.name in {".budget", *budget.MANIFESTS}:
            components.add(str(path.parent))
    totals = dict.fromkeys(components, 0)
    for name in names:
        path = root / name
        if not path.is_file() or path.resolve() != path or not size.is_source(path):
            continue
        text = budget.read_text(path)
        lines = text.splitlines(keepends=True)
        functions, issue = function_sizes(size, path, lines)
        files[name] = dict(lines=len(lines), functions=functions, issue=issue,
                           language=path.suffix or "script", fingerprint=fingerprint(text))
        markers = budget.comment_markers(path)
        sloc = sum(bool(line) and not line.startswith(markers) for line in map(str.strip, lines))
        for ancestor in Path(name).parents:
            key = str(ancestor)
            if key in totals and not budget.is_test(root / ancestor, path):
                totals[key] += sloc
    for component in sorted(components):
        directory = root / component
        limits = budget.read_budget(directory)
        projects[component] = dict(sloc=totals[component], deps=budget.project_deps(directory), limits=limits)
    return dict(files=files, projects=projects, sloc=totals["."],
                maxFile=size.limit("DL_MAX_FILE"), maxFunction=size.limit("DL_MAX_FUNC"),
                lizard=importlib.util.find_spec("lizard") is not None)

def main():
    root = Path.cwd()
    names = load_budget().dl.git_files(str(root))
    if names is None:
        raise ValueError("refactoring baselines require a Git worktree")
    names = sorted({str(Path(name).relative_to(root)) for name in names})
    print(json.dumps(structures(root, names), separators=(",", ":")))


if __name__ == "__main__":
    main()
