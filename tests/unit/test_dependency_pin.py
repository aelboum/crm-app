"""The SaaS-OS dependency is the approved commit, in the manifest, the
lockfile and the installed package (decisions K3, K3.1 and K3.2)."""

from __future__ import annotations

import json
import re
import tomllib
from importlib.metadata import distribution
from pathlib import Path

import saas_os

from tests.support import REPO_ROOT

APPROVED_PIN = "b03d87a5272924d1e413c144dc5c3b41ac430580"
APPROVED_REQUIREMENT = f"saas-os @ git+https://github.com/aelboum/saas-os@{APPROVED_PIN}"


def _manifest() -> dict[str, object]:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_manifest_declares_exactly_the_approved_requirement() -> None:
    project = _manifest()["project"]
    assert isinstance(project, dict)
    dependencies = project["dependencies"]
    saas_os_requirements = [d for d in dependencies if re.match(r"saas[-_]os\b", d)]
    assert saas_os_requirements == [APPROVED_REQUIREMENT]


def test_manifest_has_no_other_source_for_saas_os() -> None:
    tool = _manifest().get("tool", {})
    assert isinstance(tool, dict)
    uv = tool.get("uv", {})
    assert isinstance(uv, dict)
    assert "saas-os" not in uv.get("sources", {})


def test_lockfile_resolves_the_approved_commit() -> None:
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    entries = [p for p in lock["package"] if p["name"] == "saas-os"]
    assert len(entries) == 1
    source = entries[0]["source"]
    assert source == {
        "git": f"https://github.com/aelboum/saas-os?rev={APPROVED_PIN}#{APPROVED_PIN}"
    }


def test_installed_package_is_the_approved_commit_and_not_editable() -> None:
    direct_url = json.loads(distribution("saas-os").read_text("direct_url.json") or "{}")
    assert direct_url.get("url") == "https://github.com/aelboum/saas-os"
    assert direct_url.get("vcs_info", {}).get("commit_id") == APPROVED_PIN
    assert "dir_info" not in direct_url  # an editable or local-path install


def test_installed_package_resolves_from_site_packages() -> None:
    location = Path(saas_os.__file__).resolve()
    # The project virtual environment lives in the repository; the package
    # must still be the installed copy, never a source tree on the path.
    assert "site-packages" in location.parts
    assert REPO_ROOT / "src" not in location.parents


def test_dependency_urls_carry_no_credentials() -> None:
    for name in ("pyproject.toml", "uv.lock"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"https://[^/\s\"']*@github\.com", text), name


def test_this_repository_defines_no_saas_os_package() -> None:
    assert not (REPO_ROOT / "src" / "saas_os").exists()
    assert not (REPO_ROOT / "saas_os").exists()
