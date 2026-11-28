"""Independent check for grouping a parametrized Python import test."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
from types import SimpleNamespace
import xml.etree.ElementTree as ET


TEMPLATE = '''
@pytest.mark.parametrize("names", [MODULE_NAMES[i:i + SIZE] for i in range(0, len(MODULE_NAMES), SIZE)])
def test_a_module_imports(names):
    failures = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception:
            failures.append(traceback.format_exc())
    if failures:
        pytest.fail("\\n".join(failures))
'''


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def original(root, baseline, path):
    expected = baseline["files"][path][1][1]
    data = subprocess.check_output(["git", "show", f'{baseline["base"]}:{path}'], cwd=root)
    require(hashlib.sha256(data).hexdigest() == expected, "Original file differs from the recorded baseline")
    return data


def candidate(root, path):
    file = root / path
    require(file.resolve() == file and file.is_file(), "Expected a regular project file")
    return file.read_bytes()


def without_docstring(function):
    if ast.get_docstring(function) is not None:
        function.body.pop(0)
    return ast.dump(function)


def extract(data):
    tree = ast.parse(data)
    tests = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "test_a_module_imports"]
    require(len(tests) == 1, "Expected one test_a_module_imports definition")
    test, = tests
    tree.body.remove(test)
    return tree, test


def compare(before, after):
    original_tree, prior = extract(before)
    candidate_tree, grouped = extract(after)
    reference = ast.parse(
        '@pytest.mark.parametrize("name", MODULE_NAMES)\ndef test_a_module_imports(name):\n importlib.import_module(name)'
    ).body[0]
    require(without_docstring(prior) == ast.dump(reference), "Original test is not the single-import reference")
    require(any(isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MODULE_NAMES"
                for t in node.targets) for node in original_tree.body), "Original module discovery is missing")
    # The added import must introduce no new shadowing or executable statements.
    extra = ast.dump(ast.parse("import traceback").body[0])
    require(all(not isinstance(node, ast.Name) or node.id != "traceback" for node in ast.walk(original_tree)),
            "Original suite already uses traceback")
    added = [node for node in candidate_tree.body if ast.dump(node) == extra]
    require(len(added) == 1 and added[0].lineno < grouped.lineno, "Import traceback before the grouped test")
    candidate_tree.body.remove(added[0])
    require(ast.dump(candidate_tree) == ast.dump(original_tree), "Module discovery or another test changed")
    sizes = {node.value for node in ast.walk(grouped)
             if isinstance(node, ast.Constant) and type(node.value) is int and node.value >= 3}
    require(len(sizes) == 1, "Expected one literal batch size")
    size, = sizes
    require(3 <= size <= 256, "Unsupported batch size")
    expected = ast.parse(TEMPLATE.replace("SIZE", str(size))).body[0]
    require(without_docstring(grouped) == ast.dump(expected), "Group body does not match the checked import/failure pattern")
    return size


def exercise(size):
    names = [f"fixture.module_{index}" for index in range(1376)]
    failures = {names[0], names[1]}
    seen, cases, errors = [], [], []

    def trace(name):
        seen.append(name)
        if name in failures:
            raise ImportError(name)

    def parametrize(_name, values):
        cases.extend(values)
        return lambda fn: fn

    scope = dict(MODULE_NAMES=names, traceback=traceback, importlib=SimpleNamespace(import_module=trace),
                 pytest=SimpleNamespace(mark=SimpleNamespace(parametrize=parametrize), fail=errors.append))
    exec(compile(TEMPLATE.replace("SIZE", str(size)), "<checked-import-pattern>", "exec"), scope)
    for group in cases:
        scope["test_a_module_imports"](group)
    require(seen == names and len(errors) == 1 and all(name in errors[0] for name in failures)
            and errors[0].count("Traceback (most recent call last)") == 2,
            "Grouped imports did not preserve order or report both failures")
    return {"imports": len(seen), "groups": len(cases), "injectedFailures": len(failures)}


def compare_ratchet(root, baseline, path, test_path):
    old = json.loads(original(root, baseline, path))
    new = json.loads(candidate(root, path))
    entry = test_path + "::test_a_module_imports"
    require(isinstance(old, list) and old.count(entry) == 1 and isinstance(new, list)
            and new == [item for item in old if item != entry], "Only the obsolete import-test ratchet entry may be removed")


def run_suite(root, test):
    with tempfile.TemporaryDirectory(prefix="deadlion-import-") as directory:
        report = Path(directory) / "tests.xml"
        env = {key: value for key, value in os.environ.items() if key != "PYTEST_ADDOPTS"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-o", "addopts=", test,
                                 "-p", "no:cacheprovider", "--junitxml", str(report)],
                                cwd=root, env=env, capture_output=True, text=True)
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        require(result.returncode == 0, f"pytest exited {result.returncode}")
        require(not re.search(r"\b[1-9]\d* (?:deselected|skipped|xfailed|xpassed)\b", result.stdout),
                "pytest only partially executed the requested file")
        cases = ET.parse(report).findall(".//testcase")
        require(any(case.get("name", "").startswith("test_a_module_imports[") for case in cases)
                and not any(case.find(kind) is not None for case in cases for kind in ("failure", "error", "skipped")),
                "Expected grouped import cases and a fully passing suite")
        return len(cases)


def main(directory, token, test, ratchet=None):
    task = json.loads((directory / "task.json").read_bytes())
    baseline = json.loads((directory / "baseline.json").read_bytes())
    root = Path(task["root"])
    require(Path.cwd() == root and task["base"] == baseline["base"], "Checkout or task baseline changed")
    size = compare(original(root, baseline, test), candidate(root, test))
    if ratchet:
        compare_ratchet(root, baseline, ratchet, test)
    metrics = exercise(size)
    metrics["passed"] = run_suite(root, test)
    require(metrics["passed"] > 1, "Expected import cases and a nonempty discovery check")
    print("Deadlion import characterization " + token + " " + json.dumps(metrics))


if __name__ == "__main__":
    try:
        directory, *args = sys.argv[1:]
        require(re.fullmatch("[a-f0-9-]{36}", args[0]), "Invalid observation identity")
        main(Path(directory), *args)
    except (KeyError, IndexError, OSError, ValueError, SyntaxError, subprocess.SubprocessError, ET.ParseError) as error:
        sys.exit(str(error))
