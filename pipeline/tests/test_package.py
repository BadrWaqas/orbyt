"""Smoke test: the package and its planned subpackages import."""

import importlib

import orbyt


def test_package_has_version():
    assert orbyt.__version__


def test_subpackages_import():
    for name in ("core", "sources", "modules", "modules.pollution_hunter"):
        importlib.import_module(f"orbyt.{name}")
