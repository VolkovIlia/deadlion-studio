"""Collect existing Suckless measures for a refactoring baseline or checkpoint."""
import ast
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


def function_sizes(size, path, lines):
    if size.is_python(path):
        try:
            tree = ast.parse("".join(lines))
        except SyntaxError:
            return {}
        return {
            f"{node.name}:{index}": size.count_function_lines(node, lines)
            for index, node in enumerate(node for node in ast.walk(tree)
                                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
        }
    try:
        import lizard
    except ImportError:
        return {}
    result = lizard.analyze_file.analyze_source_code(str(path), "".join(lines))
    return {f"{item.long_name}:{index}": item.nloc for index, item in enumerate(result.function_list)}


def structures(root, names):
    budget = load_budget()
    size = budget.dl
    files = {}
    projects = {}
    total_sloc = 0
    components = {"."}
    for name in names:
        path = root / name
        if path.resolve() != path or not path.is_file():
            continue
        if path.name in (".budget", "Cargo.toml", "package.json", "pyproject.toml", "go.mod", "config.mk"):
            components.add(str(Path(name).parent))
        if not size.is_source(path):
            continue
        lines = budget.read_text(path).splitlines(keepends=True)
        if not budget.is_test(root, path):
            total_sloc += budget.count_sloc(path)
        files[name] = dict(lines=len(lines), functions=function_sizes(size, path, lines))
    for component in sorted(components):
        directory = root / component
        if len(components) == 1 or (directory / ".budget").is_file():
            limits = budget.read_budget(directory)
            projects[component] = dict(sloc=total_sloc if component == "." else budget.project_sloc(directory),
                                       deps=budget.project_deps(directory), limits=limits)
    return dict(files=files, projects=projects, sloc=total_sloc,
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
