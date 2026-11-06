#!/usr/bin/env python3
"""Stand-in for ``opencode run`` used to test run_opencode.py without an LLM.

It accepts the same arguments the harness passes, emits opencode-style JSON
events (including ``sessionID``) and writes ``solution.sp`` into ``--dir``:

* first message of a session  -> a broken problem-1 design (no load resistor)
* any follow-up message       -> the correct design

Every received message is echoed in a ``{"type": "fake.message"}`` event so
tests can verify exactly what the agent was told.
"""

import json
import os
import sys
import uuid

BROKEN = """* broken CS amplifier (no load resistor)
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
.model pmos_model pmos level=1 kp=50e-6 vto=-0.5
Vdd Vdd 0 5
Vin Vin 0 1
Vb Vb 0 4
M1 Vout Vin 0 0 nmos_model W=50u L=1u
M2 Vout Vb Vdd Vdd pmos_model W=50u L=1u
.end
"""

FIXED = """* CS amplifier
.model nmos_model nmos level=1 kp=100e-6 vto=0.5
Vdd Vdd 0 5.0
Vin Vin 0 1.5
M1 Vout Vin 0 0 nmos_model W=50u L=1u
R1 Vout Vdd 1k
.end
"""


def main(argv):
    assert argv[0] == "run", argv
    args = argv[1:]
    opts, msg = {}, None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            msg = " ".join(args[i + 1:])
            break
        if a.startswith("--") or a in ("-m", "-s"):
            opts[a] = args[i + 1]
            i += 2
            continue
        i += 1
    ws = opts["--dir"]
    session = opts.get("--session") or opts.get("-s")
    first = session is None
    session = session or "ses_fake_" + uuid.uuid4().hex[:8]
    with open(os.path.join(ws, "solution.sp"), "w") as fh:
        fh.write(BROKEN if first else FIXED)
    for ev in ({"type": "step_start", "sessionID": session},
               {"type": "fake.message", "sessionID": session, "message": msg,
                "agents_md_present": os.path.isfile(os.path.join(ws, "AGENTS.md")),
                "config": json.load(open(os.path.join(ws, "opencode.json")))},
               {"type": "step_finish", "sessionID": session}):
        print(json.dumps(ev))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
