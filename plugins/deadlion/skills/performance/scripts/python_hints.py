"""Fast post-edit checks for repeated sorting and copying in Python loops."""

import ast


def hints(path, source):
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as err:
        raise ValueError(f"invalid Python at {path}:{err.lineno}") from err
    pending = [(tree, None)]
    while pending:
        node, loop = pending.pop()
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            loop = None
        if isinstance(node, (ast.For, ast.AsyncFor)):
            pending.extend((child, node) for child in node.body)
            pending.extend(
                (child, loop) for child in (node.iter, node.target, *node.orelse)
            )
            continue
        pending.extend((child, loop) for child in ast.iter_child_nodes(node))
        if loop is None or not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr == "copy" and not node.args:
            rule = "dl-py-copy-loop"
            message = "Check the container type, copy size, aliasing and whether mutation requires a fresh copy."
        elif isinstance(fn, ast.Name) and fn.id == "sorted" and len(node.args) == 1:
            if (
                isinstance(node.args[0], ast.Name)
                and isinstance(loop.target, ast.Name)
                and node.args[0].id == loop.target.id
            ):
                continue
            rule = "dl-py-repeat-sort"
            message = "Check whether the sort input or key changes between iterations."
        else:
            continue
        target = fn.value if isinstance(fn, ast.Attribute) else node.args[0]
        yield dict(
            semanticTarget={"line": target.lineno, "symbol": target.id} if isinstance(target, ast.Name) else None,
            file=str(path),
            line=node.lineno,
            source="python_hints",
            range=dict(startLine=node.lineno, startColumn=node.col_offset + 1,
                       endLine=node.end_lineno, endColumn=node.end_col_offset + 1, unit="UTF-8 byte"),
            rule=rule,
            severity="INFO",
            confidence="heuristic",
            explanation=message,
            confirm="Compare wall time and allocations across loop and input sizes.",
        )
