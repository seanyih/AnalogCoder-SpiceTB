"""Command-line interface.

    python -m spicetb check  -t 5 my_design.sp [--json] [--keep DIR]
    python -m spicetb list
    python -m spicetb show   -t 5            # print the problem description
    python -m spicetb selftest [-t 1 -t 2]   # run the reference designs

Exit status of ``check``: 0 = pass, 1 = fail, 2 = usage / environment error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .ngspice import NgspiceNotFound, find_ngspice
from .tasks import ROOT, TASKS, check, get_task


def _check(args) -> int:
    t = get_task(args.task)
    try:
        text = sys.stdin.read() if args.netlist == "-" else open(args.netlist).read()
    except OSError as exc:
        print(f"cannot read netlist: {exc}", file=sys.stderr)
        return 2
    res = check(t.id, text, timeout=args.timeout, keep_dir=args.keep)
    if args.json:
        print(json.dumps(res.to_dict(), indent=2, default=float))
    else:
        print(f"[{t.name}] {'PASS' if res.passed else 'FAIL'}")
        print(res.feedback())
    return 0 if res.passed else 1


def _list(args) -> int:
    for t in TASKS.values():
        print(f"{t.name}  {t.level:<6}  {t.type:<14} in: {', '.join(t.inputs) or '-':<36} "
              f"out: {', '.join(t.outputs):<12} {t.circuit}")
    return 0


def _show(args) -> int:
    print(open(get_task(args.task).problem_file).read())
    return 0


def _selftest(args) -> int:
    ids = [get_task(x).id for x in args.task] if args.task else list(TASKS)
    failed = []
    for i in ids:
        t = TASKS[i]
        path = os.path.join(ROOT, "reference", f"{t.name}.sp")
        t0 = time.time()
        res = check(i, open(path).read(), timeout=args.timeout)
        status = "PASS" if res.passed else "FAIL"
        print(f"{t.name} {status} ({time.time() - t0:5.1f}s) {t.circuit[:60]}")
        if not res.passed:
            print("    " + res.feedback().replace("\n", "\n    "))
            failed.append(t.name)
    print(f"\n{len(ids) - len(failed)}/{len(ids)} reference designs pass.")
    return 1 if failed else 0


def main(argv: list[str] | None = None, task: int | None = None) -> int:
    """Entry point.  ``task`` pre-selects a problem (used by checkers/check_pNN.py)."""
    if task is not None:
        p = argparse.ArgumentParser(prog=f"check_p{task:02d}.py",
                                    description=f"Check a SPICE netlist against problem {task}: "
                                                f"{TASKS[task].circuit}")
        p.add_argument("netlist", help="netlist file ('-' for stdin)")
        p.add_argument("--json", action="store_true", help="print the result as JSON")
        p.add_argument("--keep", metavar="DIR", help="keep the generated decks and simulator logs in DIR")
        p.add_argument("--timeout", type=int, default=300, help="per-simulation timeout in seconds")
        args = p.parse_args(argv)
        args.task = task
        func = _check
    else:
        p = argparse.ArgumentParser(prog="spicetb", description="SPICE port of the AnalogCoder benchmark")
        sub = p.add_subparsers(dest="cmd", required=True)
        c = sub.add_parser("check", help="check a netlist against a problem")
        c.add_argument("-t", "--task", required=True, help="problem id (1..24 or p01..p24)")
        c.add_argument("netlist", help="netlist file ('-' for stdin)")
        c.add_argument("--json", action="store_true")
        c.add_argument("--keep", metavar="DIR")
        c.add_argument("--timeout", type=int, default=300)
        c.set_defaults(func=_check)
        sub.add_parser("list", help="list the problems").set_defaults(func=_list)
        s = sub.add_parser("show", help="print a problem description")
        s.add_argument("-t", "--task", required=True)
        s.set_defaults(func=_show)
        st = sub.add_parser("selftest", help="check the reference designs")
        st.add_argument("-t", "--task", action="append")
        st.add_argument("--timeout", type=int, default=300)
        st.set_defaults(func=_selftest)
        args = p.parse_args(argv)
        func = args.func
    try:
        find_ngspice()
    except NgspiceNotFound as exc:
        if func is not _list and func is not _show:
            print(str(exc), file=sys.stderr)
            return 2
    try:
        return func(args)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
