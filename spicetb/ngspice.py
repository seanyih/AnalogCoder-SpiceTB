"""Thin wrapper around the ngspice command-line simulator.

Every simulation is a separate batch run (``ngspice -b``) of a self-contained
deck: the (sanitised) candidate netlist, optional test-fixture cards, and a
``.control`` block written by the testbench that runs exactly one analysis
and writes its vectors to a binary raw file.  Running one analysis per deck
means that a failed analysis can never be confused with stale data from a
previous plot.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

import numpy as np

DEFAULT_TIMEOUT = 300  # seconds


class NgspiceNotFound(RuntimeError):
    pass


def find_ngspice() -> str:
    """Locate the ngspice executable.

    Order: $NGSPICE, ./third_party/ngspice/bin/ngspice (built by
    scripts/install_ngspice.sh), then $PATH.
    """
    env = os.environ.get("NGSPICE")
    if env:
        # simulations run in temporary directories, so resolve relative paths now
        return os.path.abspath(env) if os.sep in env else (shutil.which(env) or env)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local = os.path.join(here, "third_party", "ngspice", "bin", "ngspice")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    path = shutil.which("ngspice")
    if path:
        return path
    raise NgspiceNotFound(
        "ngspice executable not found. Install it (e.g. `apt install ngspice`, "
        "`conda install -c conda-forge ngspice`, or `scripts/install_ngspice.sh`) "
        "or point $NGSPICE at the binary."
    )


# --------------------------------------------------------------------------
# Raw file parsing
# --------------------------------------------------------------------------

@dataclass
class Plot:
    name: str                       # e.g. "Operating Point", "AC Analysis"
    variables: list[str]            # lower-case vector names, e.g. "v(vout)"
    data: dict[str, np.ndarray]     # name -> array (complex for AC)

    def vec(self, name: str) -> np.ndarray:
        key = name.lower()
        if key in self.data:
            return self.data[key]
        # allow "vout" as a short-hand for "v(vout)"
        if f"v({key})" in self.data:
            return self.data[f"v({key})"]
        raise KeyError(name)

    def has(self, name: str) -> bool:
        try:
            self.vec(name)
            return True
        except KeyError:
            return False

    @property
    def scale(self) -> np.ndarray:
        return self.data[self.variables[0]]

    def node_voltages(self) -> dict[str, float]:
        """Node name -> first-point real voltage (for operating points)."""
        out = {}
        for v in self.variables:
            m = re.fullmatch(r"v\((.+)\)", v)
            if m:
                out[m.group(1)] = float(np.real(self.data[v][0]))
        return out


def parse_raw(path: str) -> list[Plot]:
    """Parse an ngspice raw file (binary or ascii)."""
    with open(path, "rb") as fh:
        blob = fh.read()
    plots: list[Plot] = []
    pos = 0
    while pos < len(blob):
        header = {}
        variables: list[str] = []
        # read header lines
        while True:
            end = blob.find(b"\n", pos)
            if end < 0:
                return plots
            line = blob[pos:end].decode("latin-1")
            pos = end + 1
            if line.strip() == "":
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower()
            if key == "variables":
                nvars = int(header["no. variables"])
                for _ in range(nvars):
                    end = blob.find(b"\n", pos)
                    vline = blob[pos:end].decode("latin-1")
                    pos = end + 1
                    parts = vline.split()
                    variables.append(parts[1].lower())
                continue
            if key in ("binary", "values"):
                mode = key
                break
            header[key] = val.strip()
        nvars = int(header["no. variables"])
        npts = int(header["no. points"])
        complex_ = "complex" in header.get("flags", "").lower()
        if mode == "binary":
            width = 2 if complex_ else 1
            count = nvars * npts * width
            arr = np.frombuffer(blob, dtype="<f8", count=count, offset=pos)
            pos += count * 8
            arr = arr.reshape(npts, nvars * width) if npts else arr.reshape(0, nvars * width)
            if complex_:
                arr = arr[:, 0::2] + 1j * arr[:, 1::2]
        else:  # ascii
            vals = []
            for _ in range(npts):
                row = []
                for k in range(nvars):
                    end = blob.find(b"\n", pos)
                    line = blob[pos:end].decode("latin-1")
                    pos = end + 1
                    tok = line.split()[-1] if k else line.split()[1]
                    if complex_:
                        re_, im_ = tok.split(",")
                        row.append(complex(float(re_), float(im_)))
                    else:
                        row.append(float(tok))
                vals.append(row)
            arr = np.array(vals, dtype=complex if complex_ else float).reshape(npts, nvars)
        data = {name: arr[:, i].copy() for i, name in enumerate(variables)}
        plots.append(Plot(header.get("plotname", ""), variables, data))
    return plots


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------

_FLOAT_RE = re.compile(r"singular matrix:\s*check nodes?\s+(\S+)", re.I)

# ngspice lines we never want to surface as errors
_BENIGN = (
    "unsupported ngspice version",
    "no compatibility mode selected",
)


@dataclass
class SimResult:
    ok: bool                          # analysis produced the expected plot
    plot: Plot | None
    log: str                          # full stdout+stderr
    errors: list[str] = field(default_factory=list)   # error lines
    floating_nodes: list[str] = field(default_factory=list)
    timed_out: bool = False

    def error_text(self, limit: int = 20) -> str:
        lines = list(self.errors)
        if self.timed_out:
            lines.append("Simulation timed out.")
        if not lines and not self.ok:
            lines.append("Simulation failed (no results produced).")
        return "\n".join(lines[:limit])


def _extract_errors(log: str) -> tuple[list[str], list[str]]:
    errors, floating = [], []
    for line in log.splitlines():
        low = line.lower().strip()
        if not low or any(b in low for b in _BENIGN):
            continue
        m = _FLOAT_RE.search(line)
        if m:
            node = m.group(1)
            if node not in floating:
                floating.append(node)
            continue
        if "error" in low or "timestep too small" in low or "aborted" in low:
            if line.strip() not in errors:
                errors.append(line.strip())
    return errors, floating


_PLOT_PREFIX = {
    "op": "operating point",
    "dc": "dc transfer",
    "ac": "ac analysis",
    "tran": "transient analysis",
}


def simulate(body: str, analysis: str, saves: list[str] | None = None,
             timeout: int = DEFAULT_TIMEOUT, keep_dir: str | None = None) -> SimResult:
    """Run one analysis on ``body`` (netlist cards, no title / .end).

    analysis: a ngspice control-language analysis command, e.g. ``op``,
              ``dc vin 0 5 0.01``, ``ac dec 2 100 1000``, ``tran 1u 10m``.
    saves:    vectors to save (``save`` command arguments).  ``None`` means
              ngspice default (all node voltages and branch currents).
    """
    exe = find_ngspice()
    kind = analysis.split()[0].lower()
    tmp = keep_dir or tempfile.mkdtemp(prefix="spicetb_")
    os.makedirs(tmp, exist_ok=True)
    deck = os.path.join(tmp, "deck.cir")
    raw = os.path.join(tmp, "out.raw")
    if os.path.exists(raw):
        os.remove(raw)
    ctrl = ["set filetype=binary"]
    if saves:
        ctrl.append("save " + " ".join(saves))
    ctrl.append(analysis)
    ctrl.append(f"write {os.path.basename(raw)}")
    ctrl.append("quit")
    text = "* spicetb deck\n" + body.rstrip() + "\n.control\n" + "\n".join(ctrl) + "\n.endc\n.end\n"
    with open(deck, "w") as fh:
        fh.write(text)
    timed_out = False
    try:
        proc = subprocess.run([exe, "-b", os.path.basename(deck)], cwd=tmp,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, timeout=timeout)
        log = proc.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        log = (exc.stdout or b"").decode("utf-8", "replace")
    errors, floating = _extract_errors(log)
    plot = None
    if not timed_out and os.path.exists(raw):
        try:
            plots = parse_raw(raw)
            want = _PLOT_PREFIX.get(kind, "")
            for p in plots:
                if p.name.lower().startswith(want):
                    plot = p
        except Exception as exc:  # pragma: no cover - corrupted raw
            errors.append(f"spicetb: could not parse simulator output: {exc}")
    if keep_dir is None:
        shutil.rmtree(tmp, ignore_errors=True)
    ok = plot is not None and bool(plot.data) and len(plot.scale) > 0 and not errors
    return SimResult(ok=bool(ok), plot=plot, log=log, errors=errors,
                     floating_nodes=floating, timed_out=timed_out)
