"""Self-tests for the SPICE testbench.

* every reference design (reference/pNN.sp) must PASS its checker;
* every netlist in tests/negative/ must FAIL, at the stage named in its
  header line ``* task: N  expect: <stage>``.

Run with ``python -m pytest tests`` or ``python tests/test_testbench.py``.
"""

import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from spicetb.tasks import TASKS, check  # noqa: E402

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None

NEGATIVE = sorted(glob.glob(os.path.join(ROOT, "tests", "negative", "*.sp")))


def _header(path):
    first = open(path).readline()
    m = re.search(r"task:\s*(\d+)\s+expect:\s*([\w-]+)", first)
    assert m, f"{path}: missing '* task: N  expect: stage' header"
    return int(m.group(1)), m.group(2)


def check_reference(task_id):
    path = os.path.join(ROOT, "reference", f"p{task_id:02d}.sp")
    res = check(task_id, open(path).read())
    assert res.passed, res.feedback()


def check_negative(path):
    task_id, stage = _header(path)
    res = check(task_id, open(path).read())
    assert not res.passed, f"{os.path.basename(path)} unexpectedly passed:\n{res.feedback()}"
    assert res.stage == stage, (f"{os.path.basename(path)}: expected failure at '{stage}', "
                                f"got '{res.stage}':\n{res.feedback()}")


if pytest:
    @pytest.mark.parametrize("task_id", list(TASKS))
    def test_reference(task_id):
        check_reference(task_id)

    @pytest.mark.parametrize("path", NEGATIVE, ids=[os.path.basename(p) for p in NEGATIVE])
    def test_negative(path):
        check_negative(path)


if __name__ == "__main__":
    bad = 0
    for i in TASKS:
        try:
            check_reference(i)
            print(f"reference p{i:02d}: ok")
        except AssertionError as exc:
            bad += 1
            print(f"reference p{i:02d}: FAILED\n{exc}")
    for p in NEGATIVE:
        try:
            check_negative(p)
            print(f"negative {os.path.basename(p)}: ok")
        except AssertionError as exc:
            bad += 1
            print(f"negative {os.path.basename(p)}: FAILED\n{exc}")
    print("all good" if not bad else f"{bad} problem(s)")
    sys.exit(1 if bad else 0)
