"""SPICE (ngspice) testbench for the AnalogCoder 24-problem analog design benchmark."""

from .tasks import TASKS, Result, check, get_task

__all__ = ["TASKS", "Result", "check", "get_task"]
