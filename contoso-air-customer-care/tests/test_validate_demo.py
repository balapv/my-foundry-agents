"""Offline checks for scripts/validate_demo.py."""

import importlib.util
import sys

from agent import foundry_common as fc


def _load():
    spec = importlib.util.spec_from_file_location("validate_demo", fc.REPO_ROOT / "scripts" / "validate_demo.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vd = _load()


def test_missing_parent_package_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(vd, "REQUIRED_PACKAGES", ("json", "no_such_pkg.sub"))
    report = vd.Report()
    vd.check_local(report)
    packages = next(c for c in report.checks if c.name == "Python packages")
    assert packages.status == "FAIL"
    assert "no_such_pkg.sub" in packages.detail
    assert "json" not in packages.detail
