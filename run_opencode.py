#!/usr/bin/env python3
"""Run the SPICE AnalogCoder benchmark with an opencode agent.

For every (problem, trial) the harness

1. creates a fresh, isolated workspace *outside* this repository (its own git
   root, so opencode cannot see the testbench, the reference designs or this
   repo's files), containing only
     - AGENTS.md          (agent rules; default: agent/AGENTS.md, see --agents)
     - opencode.json      (tool permissions)
     - the library files the problem provides (e.g. opamp.lib);
2. sends the problem description (problems/pNN.md) as the *only* user message;
3. checks ``solution.sp`` written by the agent with the testbench;
4. optionally continues the same opencode session with feedback:
     --feedback none    one round only (default)
     --feedback binary  the single word "wrong", nothing else
     --feedback error   the testbench report (simulator errors and the
                        failed check with its diagnostic)
   until the design passes or --max-rounds is reached.

Example:

    python run_opencode.py --model anthropic/claude-sonnet-4-5 --all \
        --feedback error --max-rounds 5 --trials 5 --jobs 4

Results are written to --out (default runs/<timestamp>): one directory per
problem/trial with every round's netlist, testbench result and opencode event
log, plus results.jsonl and summary.md.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from spicetb.tasks import TASKS, Result, check, get_task  # noqa: E402

SOLUTION = "solution.sp"
WRONG = "wrong"

ALLOW_SIM_NOTE = """

## Simulation

You may run `ngspice` (batch mode, e.g. `ngspice -b test.cir`) inside this
directory to simulate your own design. You may write your own small test
decks for this. You still have no access to the evaluation testbench.
"""


def opencode_config(allow_bash: bool) -> dict:
    return {
        "$schema": "https://opencode.ai/config.json",
        "permission": {
            "read": "allow",
            "edit": "allow",
            "glob": "allow",
            "grep": "allow",
            "list": "allow",
            "bash": "allow" if allow_bash else "deny",
            "webfetch": "deny",
            "websearch": "deny",
            "external_directory": "deny",
            "question": "deny",
        },
    }


def make_workspace(task, agents_text: str, allow_bash: bool, base: str | None) -> str:
    ws = tempfile.mkdtemp(prefix=f"spicetb_{task.name}_", dir=base)
    with open(os.path.join(ws, "AGENTS.md"), "w") as fh:
        fh.write(agents_text + (ALLOW_SIM_NOTE if allow_bash else ""))
    with open(os.path.join(ws, "opencode.json"), "w") as fh:
        json.dump(opencode_config(allow_bash), fh, indent=2)
    for name, path in task.lib_paths().items():
        shutil.copy(path, os.path.join(ws, name))
    # make the workspace its own project root so opencode does not walk up
    # into a surrounding repository (and its AGENTS.md / files)
    subprocess.run(["git", "init", "-q"], cwd=ws, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return ws


def run_opencode(args, ws: str, message: str, session: str | None, log_path: str) -> tuple[str | None, str]:
    cmd = [args.opencode, "run", "--format", "json", "--dir", ws]
    if args.model:
        cmd += ["-m", args.model]
    if args.variant:
        cmd += ["--variant", args.variant]
    if args.agent:
        cmd += ["--agent", args.agent]
    if session:
        cmd += ["--session", session]
    cmd += ["--", message]
    env = dict(os.environ)
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=ws, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=args.agent_timeout)
        out, err, status = proc.stdout, proc.stderr, f"exit {proc.returncode}"
    except subprocess.TimeoutExpired as exc:
        out, err, status = exc.stdout or b"", exc.stderr or b"", "timeout"
    out = out.decode("utf-8", "replace") if isinstance(out, bytes) else out
    err = err.decode("utf-8", "replace") if isinstance(err, bytes) else err
    with open(log_path, "w") as fh:
        fh.write(out)
    if err.strip():
        with open(log_path + ".stderr", "w") as fh:
            fh.write(err)
    sid = session
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("sessionID"):
            sid = ev["sessionID"]
            break
    return sid, f"{status}, {time.time() - t0:.0f}s"


def run_one(args, task_id: int, trial: int, agents_text: str) -> dict:
    task = get_task(task_id)
    prompt = open(task.problem_file).read()
    out_dir = os.path.join(args.out, task.name, f"trial{trial}")
    os.makedirs(out_dir, exist_ok=True)
    ws = make_workspace(task, agents_text, args.allow_bash, args.workspace_base)
    rounds = 1 if args.feedback == "none" else args.max_rounds
    session = None
    history = []
    message = prompt
    passed_round = None
    try:
        for k in range(1, rounds + 1):
            sid, status = run_opencode(args, ws, message, session, os.path.join(out_dir, f"round{k}_opencode.jsonl"))
            session = sid or session
            sol = os.path.join(ws, SOLUTION)
            if os.path.isfile(sol):
                text = open(sol, errors="replace").read()
                shutil.copy(sol, os.path.join(out_dir, f"round{k}_{SOLUTION}"))
                res = check(task.id, text, timeout=args.sim_timeout)
            else:
                res = Result(task.id, False, "input",
                             f"No {SOLUTION} was found in the working directory. Write the complete "
                             f"netlist to ./{SOLUTION}.")
            with open(os.path.join(out_dir, f"round{k}_result.json"), "w") as fh:
                json.dump(res.to_dict(), fh, indent=2, default=float)
            history.append({"round": k, "passed": res.passed, "stage": res.stage, "agent": status})
            print(f"[{task.name} t{trial} r{k}] {'PASS' if res.passed else 'FAIL'} "
                  f"({res.stage}; agent {status})", flush=True)
            if res.passed:
                passed_round = k
                break
            if k == rounds:
                break
            if session is None:
                print(f"[{task.name} t{trial}] no opencode session id; cannot continue", flush=True)
                break
            message = WRONG if args.feedback == "binary" else res.feedback()
            with open(os.path.join(out_dir, f"round{k + 1}_feedback.txt"), "w") as fh:
                fh.write(message)
    finally:
        if args.keep_workspace:
            dst = os.path.join(out_dir, "workspace")
            shutil.copytree(ws, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
        shutil.rmtree(ws, ignore_errors=True)
    rec = {"task": task.id, "trial": trial, "passed": passed_round is not None,
           "passed_round": passed_round, "rounds": len(history), "session": session,
           "history": history, "model": args.model, "feedback": args.feedback}
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(rec, fh, indent=2)
    return rec


def write_summary(args, records: list[dict]):
    with open(os.path.join(args.out, "results.jsonl"), "w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    lines = [f"# Results: {args.model or '(opencode default model)'}", "",
             f"feedback = `{args.feedback}`, max rounds = {1 if args.feedback == 'none' else args.max_rounds}, "
             f"trials per problem = {args.trials}", "",
             "| Problem | Pass@1 (round 1) | Solved within rounds | Mean rounds to pass |",
             "|---|---|---|---|"]
    tot1 = totn = 0
    solved = 0
    by_task: dict[int, list[dict]] = {}
    for r in records:
        by_task.setdefault(r["task"], []).append(r)
    for tid in sorted(by_task):
        rs = by_task[tid]
        p1 = sum(1 for r in rs if r["passed_round"] == 1) / len(rs)
        pn = sum(1 for r in rs if r["passed"]) / len(rs)
        rounds = [r["passed_round"] for r in rs if r["passed"]]
        mean_r = f"{sum(rounds) / len(rounds):.2f}" if rounds else "-"
        tot1 += p1
        totn += pn
        solved += pn > 0
        lines.append(f"| p{tid:02d} | {p1:.0%} | {pn:.0%} | {mean_r} |")
    n = max(len(by_task), 1)
    lines += ["", f"**Average Pass@1:** {tot1 / n:.1%}  ", f"**Average pass within rounds:** {totn / n:.1%}  ",
              f"**#Solved (at least one trial passes):** {solved}/{len(by_task)}"]
    with open(os.path.join(args.out, "summary.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument("-t", "--task", action="append", help="problem id (repeatable): 1..24 or p01..p24")
    sel.add_argument("--all", action="store_true", help="run all 24 problems")
    p.add_argument("-m", "--model", help="opencode model, provider/model (default: opencode's configured model)")
    p.add_argument("--variant", help="model variant / reasoning effort passed to opencode")
    p.add_argument("--agent", help="opencode agent to use (default: opencode's default agent)")
    p.add_argument("--feedback", choices=["none", "binary", "error"], default="none",
                   help="none: one round; binary: reply 'wrong' on failure; error: reply with the testbench report")
    p.add_argument("--max-rounds", type=int, default=5, help="maximum rounds with feedback (default 5)")
    p.add_argument("--trials", type=int, default=1, help="independent trials per problem (default 1)")
    p.add_argument("--agents", default=os.path.join(ROOT, "agent", "AGENTS.md"),
                   help="AGENTS.md to place in the workspace (default: agent/AGENTS.md)")
    p.add_argument("--allow-bash", action="store_true",
                   help="allow the agent to run shell commands in its workspace (e.g. its own ngspice runs); "
                        "a note saying so is appended to the workspace AGENTS.md")
    p.add_argument("--opencode", default=os.environ.get("OPENCODE", "opencode"), help="opencode executable")
    p.add_argument("--out", help="output directory (default runs/<timestamp>)")
    p.add_argument("--workspace-base", default=None,
                   help="parent directory for the temporary agent workspaces (must be outside this repository; "
                        "default: system temp dir)")
    p.add_argument("--keep-workspace", action="store_true", help="copy each final workspace into the output directory")
    p.add_argument("--jobs", type=int, default=1, help="parallel runs")
    p.add_argument("--agent-timeout", type=int, default=1800, help="timeout per opencode call in seconds")
    p.add_argument("--sim-timeout", type=int, default=300, help="timeout per ngspice run in seconds")
    args = p.parse_args(argv)

    if shutil.which(args.opencode) is None and not os.path.isfile(args.opencode):
        p.error(f"opencode executable '{args.opencode}' not found (install with `npm i -g opencode-ai`, "
                "or pass --opencode)")
    base = os.path.realpath(args.workspace_base or tempfile.gettempdir())
    if base == ROOT or base.startswith(ROOT + os.sep):
        p.error("--workspace-base must be outside the repository, otherwise the agent can read the testbench")
    args.workspace_base = base
    ids = list(TASKS) if args.all else [get_task(x).id for x in args.task]
    args.out = args.out or os.path.join(ROOT, "runs", dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(args.out, exist_ok=True)
    agents_text = open(args.agents).read()
    with open(os.path.join(args.out, "config.json"), "w") as fh:
        json.dump({k: v for k, v in vars(args).items()}, fh, indent=2)
    shutil.copy(args.agents, os.path.join(args.out, "AGENTS.md"))

    jobs = [(tid, k) for tid in ids for k in range(1, args.trials + 1)]
    records = []
    with cf.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        futs = [ex.submit(run_one, args, tid, k, agents_text) for tid, k in jobs]
        for f in cf.as_completed(futs):
            records.append(f.result())
    records.sort(key=lambda r: (r["task"], r["trial"]))
    write_summary(args, records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
