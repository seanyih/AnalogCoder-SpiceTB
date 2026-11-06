#!/usr/bin/env python3
"""Checker for problem 17 (see problems/p17.md).

Usage: python checkers/check_p17.py design.sp [--json] [--keep DIR]
Exit status: 0 = pass, 1 = fail, 2 = usage/environment error.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from spicetb.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(task=17))
