from __future__ import annotations

import hashlib
import json
import stat
import tomllib
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPOSITORY_ROOT / "templates"
INDEX_PATH = TEMPLATES_ROOT / "index.json"
ORIGIN_PATH = REPOSITORY_ROOT / "catalog-origin.json"
RELEASE_PATH = REPOSITORY_ROOT / "catalog-release.json"
SOURCE_INDEX_PATH = REPOSITORY_ROOT / "provenance" / "source-index.json"
PYPROJECT_PATH = REPOSITORY_ROOT / "pyproject.toml"
LOCK_PATH = REPOSITORY_ROOT / "uv.lock"
EXPECTED_SOURCE_COMMIT = "2d91d5e8ab1b8eabae74c95057a5a0139e9b4abc"
EXPECTED_SOURCE_REGISTRY_SHA256 = "5695b14933fa4be57f77f6838c85dff1be72d8813aa715e50e51869dcf65d639"
EXPECTED_CORE_REPOSITORY = "https://github.com/ob-labs/agentseek.git"
EXPECTED_CORE_COMMIT = "2d91d5e8ab1b8eabae74c95057a5a0139e9b4abc"
EXPECTED_CORE_RELEASE = "v0.1.1"


def _registry() -> dict[str, str]:
    value = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _template_directories(templates_root: Path = TEMPLATES_ROOT) -> set[str]:
    return {
        f"{type_dir.name}/{template_dir.name}"
        for type_dir in templates_root.iterdir()
        if type_dir.is_dir()
        for template_dir in type_dir.iterdir()
        if template_dir.is_dir()
    }


def _assert_self_contained_template(templates_root: Path, key: str) -> None:
    type_name, template_name = key.split("/", maxsplit=1)
    type_root = templates_root / type_name
    template_root = type_root / template_name
    for directory in (templates_root, type_root, template_root):
        assert not directory.is_symlink(), f"catalog directory must not be a symlink: {directory}"
        assert stat.S_ISDIR(directory.lstat().st_mode), f"catalog directory is not a directory: {directory}"
    for candidate in template_root.rglob("*"):
        mode = candidate.lstat().st_mode
        assert not candidate.is_symlink(), f"template path must not be a symlink: {candidate}"
        assert stat.S_ISDIR(mode) or stat.S_ISREG(mode), f"unsupported template path type: {candidate}"


def test_registry_exactly_matches_published_template_directories() -> None:
    assert set(_registry()) == _template_directories()
    assert "bub/contextseek" not in _registry()


def test_catalog_tree_contains_only_directories_and_regular_files() -> None:
    for candidate in TEMPLATES_ROOT.rglob("*"):
        mode = candidate.lstat().st_mode
        assert not candidate.is_symlink(), f"catalog path must not be a symlink: {candidate}"
        assert stat.S_ISDIR(mode) or stat.S_ISREG(mode), f"unsupported catalog path type: {candidate}"


def test_every_registered_template_is_self_contained_and_documented() -> None:
    for key in sorted(_registry()):
        template_root = TEMPLATES_ROOT / key
        assert (template_root / "README.md").is_file(), key
        _assert_self_contained_template(TEMPLATES_ROOT, key)


def test_self_containment_rejects_a_template_root_symlink(tmp_path: Path) -> None:
    templates_root = tmp_path / "templates"
    type_root = templates_root / "bub"
    outside = tmp_path / "outside"
    type_root.mkdir(parents=True)
    outside.mkdir()
    (outside / "cookiecutter.json").write_text("{}", encoding="utf-8")
    (type_root / "default").symlink_to(outside, target_is_directory=True)

    with pytest.raises(AssertionError, match="must not be a symlink"):
        _assert_self_contained_template(templates_root, "bub/default")


def test_every_template_carries_the_reviewed_core_dependency_coordinate() -> None:
    for key in sorted(_registry()):
        context = json.loads((TEMPLATES_ROOT / key / "cookiecutter.json").read_text(encoding="utf-8"))
        assert context["_agentseek_source_url"] == EXPECTED_CORE_REPOSITORY, key
        assert context["_agentseek_source_ref"] == EXPECTED_CORE_COMMIT, key


def test_catalog_provenance_matches_the_frozen_source_inventory() -> None:
    origin = json.loads(ORIGIN_PATH.read_text(encoding="utf-8"))
    source_registry = json.loads(SOURCE_INDEX_PATH.read_text(encoding="utf-8"))
    assert origin == {
        "schema_version": 1,
        "source_repository": "https://github.com/ob-labs/agentseek.git",
        "source_commit": EXPECTED_SOURCE_COMMIT,
        "source_registry_sha256": EXPECTED_SOURCE_REGISTRY_SHA256,
        "included_templates": sorted(source_registry),
        "excluded_templates": [
            {
                "path": "templates/bub/contextseek",
                "reason": (
                    "Unregistered compatibility source remains quarantined until its development locking is "
                    "remediated and reviewed."
                ),
            }
        ],
    }
    assert set(source_registry) == set(_registry())


def test_recorded_registry_digest_uses_the_frozen_source_registry_bytes() -> None:
    digest = hashlib.sha256(SOURCE_INDEX_PATH.read_bytes()).hexdigest()
    assert digest == EXPECTED_SOURCE_REGISTRY_SHA256


def test_paired_release_metadata_separates_core_dependencies_from_import_provenance() -> None:
    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    assert release == {
        "schema_version": 1,
        "catalog_release": "v0.1.1",
        "lifecycle_version": 2,
        "core_repository": EXPECTED_CORE_REPOSITORY,
        "core_commit": EXPECTED_CORE_COMMIT,
        "core_release": EXPECTED_CORE_RELEASE,
        "templates_root": "templates",
        "index_path": "templates/index.json",
    }


def test_release_metadata_matches_project_and_lock_coordinates() -> None:
    release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    project = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    lock = tomllib.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked_packages = {package["name"]: package for package in lock["package"]}

    catalog_version = release["catalog_release"].removeprefix("v")
    expected_core_dependency = f"agentseek @ git+{release['core_repository']}@{release['core_commit']}"
    expected_core_lock_source = f"{release['core_repository']}?rev={release['core_commit']}#{release['core_commit']}"

    assert project["project"]["version"] == catalog_version
    assert expected_core_dependency in project["dependency-groups"]["dev"]
    assert locked_packages["agentseek-templates"]["version"] == catalog_version
    assert locked_packages["agentseek"]["version"] == release["core_release"].removeprefix("v")
    assert locked_packages["agentseek"]["source"] == {"git": expected_core_lock_source}
