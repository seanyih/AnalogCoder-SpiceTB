"""Minimal SPICE (ngspice dialect) netlist reader used by the testbench.

The reader does *not* try to be a full SPICE parser.  It understands enough
of the syntax to

* join continuation lines and strip comments,
* reject constructs that are unsafe or that would let a design side-step
  the testbench (``.control`` blocks, ``.option`` cards, arbitrary
  ``.include`` files, behavioural sources, time-varying sources, ...),
* inline the library files that a problem provides (e.g. ``opamp.lib``),
* list top-level elements with their nodes so that checkers can locate the
  input sources, load resistors, MOSFETs, op-amp instances, ...,
* produce modified copies of the netlist (replace / remove / add cards).

Node names are case-insensitive (ngspice lower-cases everything) and both
``0`` and ``gnd`` denote ground; the reader normalises them to lower case and
``0`` respectively.
"""

from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass, field

# number of node terminals per element letter (X is variable)
NODE_COUNT = {
    "r": 2, "c": 2, "l": 2, "v": 2, "i": 2, "m": 4, "d": 2, "j": 3, "z": 3,
    "e": 4, "g": 4, "f": 2, "h": 2, "b": 2, "s": 4, "w": 2, "t": 4, "o": 4,
    "u": 3, "q": 3, "k": 0, "a": 0, "n": 0, "p": 0, "y": 0,
}

ANALYSIS_CARDS = {
    ".op", ".ac", ".dc", ".tran", ".noise", ".tf", ".sens", ".pz", ".disto",
    ".four", ".print", ".plot", ".probe", ".save", ".meas", ".measure",
    ".width", ".sp", ".pss",
}
ALLOWED_DOT = {
    ".model", ".param", ".func", ".subckt", ".ends", ".ic", ".nodeset",
    ".global", ".include", ".inc", ".lib", ".end", ".title",
}

_TIME_VARYING = re.compile(
    r"\b(ac|pulse|sin|exp|pwl|sffm|am|trnoise|trrandom|distof1|distof2|external|port)\b",
    re.I)


def norm_node(n: str) -> str:
    n = n.lower()
    return "0" if n in ("0", "gnd", "gnd!") else n


def _tokenize(text: str) -> list[str]:
    text = re.sub(r"\s*=\s*", "=", text.strip())
    return text.split()


@dataclass
class Card:
    text: str
    line: int
    depth: int = 0
    origin: str = "user"     # "user" or "lib:<file>"

    @property
    def tokens(self) -> list[str]:
        return _tokenize(self.text)

    @property
    def head(self) -> str:
        t = self.tokens
        return t[0].lower() if t else ""

    @property
    def is_dot(self) -> bool:
        return self.head.startswith(".")


@dataclass
class Element:
    name: str                 # lower case, e.g. "m1"
    letter: str               # "m"
    nodes: list[str]          # normalised node names
    tokens: list[str]         # all tokens (original case)
    index: int                # index into Netlist.cards
    model: str | None = None  # MOSFET/diode model or X subcircuit name

    @property
    def value(self) -> str | None:
        n = len(self.nodes)
        return self.tokens[1 + n] if len(self.tokens) > 1 + n else None


@dataclass
class Rules:
    """Which constructs a submission may use."""
    allowed_letters: set[str] = field(default_factory=lambda: set("rclmvi"))
    allow_user_subckt: bool = False
    allowed_x: set[str] | None = None        # allowed X targets (None: any defined)
    require_level1: bool = True


class Netlist:
    def __init__(self):
        self.cards: list[Card] = []
        self.errors: list[str] = []
        self.notes: list[str] = []
        self.lib_subckts: dict[str, list[str]] = {}
        self.user_subckts: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ parse
    @classmethod
    def parse(cls, text: str, libs: dict[str, str] | None = None,
              has_title: bool = True) -> "Netlist":
        """Parse a submitted netlist.

        libs: mapping ``basename -> absolute path`` of library files that may
              be included with ``.include``/``.lib``.
        """
        nl = cls()
        nl._parse_text(text, "user", libs or {}, has_title, included=set())
        return nl

    def _parse_text(self, text, origin, libs, has_title, included):
        raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        logical: list[tuple[int, str]] = []
        for i, line in enumerate(raw, start=1):
            if has_title and i == 1:
                continue  # SPICE convention: the first line is the title
            s = line.rstrip()
            st = s.lstrip()
            if not st or st.startswith("*"):
                continue
            # inline comments: ';', '$ ', '//'
            s = re.split(r";|\s\$\s|\s\$$|//", s)[0].rstrip()
            st = s.lstrip()
            if not st:
                continue
            if st.startswith("+"):
                if logical:
                    ln, prev = logical[-1]
                    logical[-1] = (ln, prev + " " + st[1:].strip())
                else:
                    self.errors.append(f"line {i}: continuation line '+' without a preceding card")
                continue
            logical.append((i, st))

        depth = self._depth if hasattr(self, "_depth") else 0
        in_control = False
        for ln, s in logical:
            where = f"line {ln}" if origin == "user" else f"{origin[4:]} line {ln}"
            card = Card(s, ln, depth, origin)
            head = card.head
            if in_control:
                if head == ".endc":
                    in_control = False
                continue
            if head == ".control":
                self.errors.append(f"{where}: '.control' blocks are not allowed; "
                                   "the testbench runs all analyses itself")
                in_control = True
                continue
            if head == ".end":
                break
            if head.startswith("."):
                if head in ANALYSIS_CARDS:
                    self.notes.append(f"{where}: ignored analysis/output card '{head}' "
                                      "(the testbench runs its own analyses)")
                    continue
                if head not in ALLOWED_DOT:
                    self.errors.append(f"{where}: control card '{head}' is not allowed")
                    continue
                if head in (".include", ".inc", ".lib"):
                    toks = card.tokens
                    if len(toks) < 2:
                        self.errors.append(f"{where}: '{head}' needs a file name")
                        continue
                    fname = os.path.basename(toks[1].strip("'\""))
                    if fname not in libs:
                        allowed = ", ".join(sorted(libs)) or "none"
                        self.errors.append(
                            f"{where}: including '{toks[1]}' is not allowed "
                            f"(includable library files for this problem: {allowed})")
                        continue
                    if fname in included:
                        continue
                    included.add(fname)
                    with open(libs[fname]) as fh:
                        self._depth = depth
                        self._parse_text(fh.read(), f"lib:{fname}", libs, False, included)
                        depth = self._depth
                    continue
                if head == ".title":
                    continue
                if head == ".subckt":
                    toks = card.tokens
                    if len(toks) < 2:
                        self.errors.append(f"{where}: '.subckt' needs a name")
                        continue
                    name = toks[1].lower()
                    ports = []
                    for t in toks[2:]:
                        if t.lower() == "params:" or "=" in t:
                            break
                        ports.append(norm_node(t))
                    if depth == 0:
                        target = self.lib_subckts if origin != "user" else self.user_subckts
                        if name in self.lib_subckts or name in self.user_subckts:
                            self.errors.append(f"{where}: subcircuit '{toks[1]}' is defined more than once "
                                               "(library subcircuits must not be redefined)")
                        target[name] = ports
                    self.cards.append(card)
                    depth += 1
                    continue
                if head == ".ends":
                    if depth == 0:
                        self.errors.append(f"{where}: '.ends' without matching '.subckt'")
                        continue
                    depth -= 1
                    card.depth = depth
                    self.cards.append(card)
                    continue
                self.cards.append(card)
                continue
            # element card
            if not head[0].isalpha():
                self.errors.append(f"{where}: cannot parse line '{s}'")
                continue
            self.cards.append(card)
        if origin == "user" and depth != 0:
            self.errors.append("unterminated '.subckt' definition (missing '.ends')")
        self._depth = depth

    # --------------------------------------------------------------- queries
    def _element(self, idx: int, card: Card) -> Element | None:
        toks = card.tokens
        name = toks[0].lower()
        letter = name[0]
        if letter == "x":
            rest = []
            for t in toks[1:]:
                if t.lower() == "params:" or "=" in t:
                    break
                rest.append(t)
            if not rest:
                return Element(name, letter, [], toks, idx, None)
            return Element(name, letter, [norm_node(t) for t in rest[:-1]], toks, idx,
                           rest[-1].lower())
        n = NODE_COUNT.get(letter, 0)
        nodes = [norm_node(t) for t in toks[1:1 + n]]
        model = None
        if letter == "m" and len(toks) > 5:
            model = toks[5].lower()
        elif letter == "d" and len(toks) > 3:
            model = toks[3].lower()
        return Element(name, letter, nodes, toks, idx, model)

    def elements(self, letter: str | None = None, top_only: bool = True) -> list[Element]:
        out = []
        for i, c in enumerate(self.cards):
            if c.is_dot or (top_only and c.depth != 0):
                continue
            e = self._element(i, c)
            if e and (letter is None or e.letter == letter):
                out.append(e)
        return out

    def element(self, name: str) -> Element | None:
        for e in self.elements():
            if e.name == name.lower():
                return e
        return None

    def models(self) -> dict[str, str]:
        """Top-level model name -> model type (lower case)."""
        out = {}
        for c in self.cards:
            if c.depth == 0 and c.head == ".model":
                t = c.tokens
                if len(t) >= 3:
                    out[t[1].lower()] = t[2].split("(")[0].lower()
        return out

    def mos_type(self, e: Element) -> str:
        t = self.models().get(e.model or "", "")
        return "pmos" if t.startswith("p") else "nmos"

    def sources_at(self, node: str, letter: str = "v") -> list[Element]:
        """Independent sources (top level) with a terminal on ``node``.

        Sources whose positive terminal is the node come first."""
        node = norm_node(node)
        srcs = [e for e in self.elements(letter) if node in e.nodes]
        srcs.sort(key=lambda e: 0 if e.nodes[0] == node else 1)
        return srcs

    def connected(self, node: str, letter: str) -> list[Element]:
        node = norm_node(node)
        return [e for e in self.elements(letter) if node in e.nodes]

    def unique_name(self, base: str) -> str:
        names = {e.name for e in self.elements(top_only=False)}
        name, k = base, 1
        while name.lower() in names:
            name, k = f"{base}{k}", k + 1
        return name

    # ------------------------------------------------------------ validation
    def validate(self, rules: Rules) -> list[str]:
        errs = []
        for c in self.cards:
            if c.origin != "user" or c.is_dot:
                continue
            letter = c.head[0]
            where = f"line {c.line}"
            if letter not in rules.allowed_letters:
                kind = {"e": "VCVS", "g": "VCCS", "f": "CCCS", "h": "CCVS", "b": "behavioural source",
                        "x": "subcircuit instance", "a": "XSPICE code model", "s": "switch",
                        "w": "switch", "d": "diode", "q": "BJT", "j": "JFET",
                        "n": "OSDI/Verilog-A device", "t": "transmission line",
                        "k": "mutual inductor"}.get(letter, f"'{letter.upper()}' element")
                allowed = ", ".join(sorted(x.upper() for x in rules.allowed_letters))
                errs.append(f"{where}: {kind} '{c.tokens[0]}' is not allowed in this problem "
                            f"(allowed element types: {allowed})")
                continue
            if letter in ("v", "i"):
                toks = c.tokens
                spec = " ".join(toks[3:])
                if _TIME_VARYING.search(spec):
                    errs.append(f"{where}: source '{toks[0]}' must be a plain DC source "
                                f"(found '{spec}'); the testbench applies all AC/transient stimuli itself")
            if letter == "x":
                e = self._element(0, c)
                target = e.model if e else None
                defined = set(self.lib_subckts) | set(self.user_subckts)
                if not target or target not in defined:
                    errs.append(f"{where}: instance '{c.tokens[0]}' refers to an undefined subcircuit")
                elif rules.allowed_x is not None and target not in rules.allowed_x:
                    errs.append(f"{where}: instance '{c.tokens[0]}' of '{target}' is not allowed "
                                f"(allowed subcircuits: {', '.join(sorted(rules.allowed_x))})")
        if self.user_subckts and not rules.allow_user_subckt:
            errs.append("defining your own subcircuits (.subckt) is not allowed in this problem: "
                        + ", ".join(sorted(self.user_subckts)))
        if rules.require_level1:
            for c in self.cards:
                if c.origin != "user" or c.head != ".model":
                    continue
                t = c.tokens
                mtype = t[2].split("(")[0].lower() if len(t) >= 3 else ""
                if mtype not in ("nmos", "pmos", "r", "c", "res", "cap"):
                    errs.append(f"line {c.line}: model type '{mtype}' is not allowed "
                                "(only nmos/pmos models)")
                    continue
                m = re.search(r"\blevel\s*=\s*([^\s)]+)", c.text, re.I)
                if mtype in ("nmos", "pmos") and m and m.group(1) not in ("1", "1.0"):
                    errs.append(f"line {c.line}: MOSFET model '{t[1]}' must be level=1 "
                                f"(found level={m.group(1)})")
        return errs

    # ------------------------------------------------------------- editing
    def copy(self) -> "Netlist":
        return copy.deepcopy(self)

    def replace(self, name: str, text: str) -> "Netlist":
        nl = self.copy()
        e = nl.element(name)
        if e is None:
            raise KeyError(name)
        nl.cards[e.index] = Card(text, nl.cards[e.index].line, 0, "testbench")
        return nl

    def remove(self, *names: str) -> "Netlist":
        nl = self.copy()
        idx = {e.index for e in nl.elements() if e.name in {n.lower() for n in names}}
        nl.cards = [c for i, c in enumerate(nl.cards) if i not in idx]
        return nl

    def add(self, *texts: str) -> "Netlist":
        nl = self.copy()
        for t in texts:
            nl.cards.append(Card(t, 0, 0, "testbench"))
        return nl

    def render(self) -> str:
        return "\n".join(c.text for c in self.cards) + "\n"
