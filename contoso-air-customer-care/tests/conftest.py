"""Shared test configuration: pin the simulated clock so rebased dates and times are deterministic."""

import os

os.environ["DEMO_TODAY"] = "2026-05-14"
os.environ["DEMO_TIME"] = "08:00"
os.environ.pop("DEMO_TIMEZONE", None)
os.environ.pop("DISABLE_FAULT_INJECTION", None)
