import runpy
from pathlib import Path

import pytest


HELPER = Path(__file__).resolve().parents[1] / "plugins/deadlion/omp/import-characterization.py"
RUN_SUITE = runpy.run_path(str(HELPER))["run_suite"]


@pytest.mark.parametrize(("extra", "reason"), [
    ("raise RuntimeError('collection failed')", "pytest exited 2"),
    ("def test_other(): pytest.skip('not executed')", "partially executed"),
    ("def test_other(): assert False", "pytest exited 1"),
])
def test_incomplete_import_suite_cannot_certify_changes(tmp_path, extra, reason):
    source = tmp_path / "test_imports.py"
    source.write_text("import pytest\n@pytest.mark.parametrize('name', [1])\n"
                      "def test_a_module_imports(name): assert name\n" + extra + "\n")
    with pytest.raises(ValueError, match=reason):
        RUN_SUITE(tmp_path, source.name)
