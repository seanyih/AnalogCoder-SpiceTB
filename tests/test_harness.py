"""Tests for run_opencode.py using tests/fake_opencode.py instead of a real agent."""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import run_opencode  # noqa: E402

FAKE = os.path.join(ROOT, "tests", "fake_opencode.py")


def _run(feedback, rounds=3):
    out = tempfile.mkdtemp(prefix="spicetb_harness_test_")
    os.chmod(FAKE, 0o755)
    rc = run_opencode.main(["-t", "1", "--opencode", FAKE, "--feedback", feedback,
                            "--max-rounds", str(rounds), "--out", out])
    assert rc == 0
    recs = [json.loads(line) for line in open(os.path.join(out, "results.jsonl"))]
    return out, recs[0]


def _events(path):
    return [json.loads(line) for line in open(path) if line.strip()]


def test_no_feedback_single_round():
    out, rec = _run("none")
    assert rec["rounds"] == 1 and not rec["passed"]
    ev = [e for e in _events(os.path.join(out, "p01", "trial1", "round1_opencode.jsonl"))
          if e["type"] == "fake.message"][0]
    # the only user message is the problem description
    assert ev["message"] == open(os.path.join(ROOT, "problems", "p01.md")).read()
    assert ev["agents_md_present"]
    assert ev["config"]["permission"]["bash"] == "deny"
    assert ev["config"]["permission"]["external_directory"] == "deny"


def test_binary_feedback_is_one_word():
    out, rec = _run("binary")
    assert rec["passed"] and rec["passed_round"] == 2
    d = os.path.join(out, "p01", "trial1")
    assert open(os.path.join(d, "round2_feedback.txt")).read() == "wrong"
    ev = [e for e in _events(os.path.join(d, "round2_opencode.jsonl")) if e["type"] == "fake.message"][0]
    assert ev["message"] == "wrong"


def test_error_feedback_contains_diagnostic():
    out, rec = _run("error")
    assert rec["passed"] and rec["passed_round"] == 2
    fb = open(os.path.join(out, "p01", "trial1", "round2_feedback.txt")).read()
    assert "operating-point" in fb and "There is no resistance in the netlist" in fb


if __name__ == "__main__":
    test_no_feedback_single_round()
    test_binary_feedback_is_one_word()
    test_error_feedback_contains_diagnostic()
    print("harness tests ok")
