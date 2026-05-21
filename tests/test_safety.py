"""Tests for shared path-safety helpers."""
import os
import pytest
from pathlib import Path
from scripts.safety import (
    is_hidden,
    is_within_home,
    is_safe_destination,
)


# ---------- is_hidden ----------

def test_is_hidden_dotfile_at_root(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    f = home / ".bashrc"
    f.touch()
    assert is_hidden(f.relative_to(tmp_path))


def test_is_hidden_dotdir_in_path(tmp_path):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    f = home / ".ssh" / "id_rsa"
    f.touch()
    assert is_hidden(f.relative_to(tmp_path))


def test_is_hidden_normal_file(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    f = home / "Downloads" / "report.pdf"
    f.parent.mkdir()
    f.touch()
    assert not is_hidden(f.relative_to(tmp_path))


# ---------- is_within_home ----------

def test_is_within_home_direct_child(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "Downloads").mkdir()
    assert is_within_home(home / "Downloads", home)


def test_is_within_home_rejects_parent(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert not is_within_home(tmp_path, home)


def test_is_within_home_rejects_etc(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert not is_within_home("/etc", home)


def test_is_within_home_rejects_path_traversal(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    # /home/user/../../../etc
    bad = home / ".." / ".." / "etc"
    assert not is_within_home(bad, home)


def test_is_within_home_rejects_symlink_escape(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sneaky = home / "looks_local"
    sneaky.symlink_to(outside)
    # After resolving, sneaky points outside home → must reject
    assert not is_within_home(sneaky, home)


def test_is_within_home_rejects_blocklisted_dotdir(tmp_path):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    assert not is_within_home(home / ".ssh", home)
    assert not is_within_home(home / ".ssh" / "id_rsa", home)


def test_is_within_home_allows_resolved_symlink_inside(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    inside = home / "Documents"
    inside.mkdir()
    link = home / "DocsLink"
    link.symlink_to(inside)
    assert is_within_home(link, home)


# ---------- is_safe_destination ----------

def test_is_safe_destination_home_root(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert is_safe_destination(home, home)


def test_is_safe_destination_normal_subfolder(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert is_safe_destination(home / "Legal", home)


def test_is_safe_destination_rejects_any_dotdir(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    # Even non-blocklisted dotdirs are rejected as destinations
    assert not is_safe_destination(home / ".secret", home)
    assert not is_safe_destination(home / "Documents" / ".hidden", home)


def test_is_safe_destination_rejects_outside_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert not is_safe_destination("/etc", home)
    assert not is_safe_destination(tmp_path, home)


def test_is_safe_destination_rejects_symlink_escape(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "etc_clone"
    outside.mkdir()
    evil = home / "Legal"  # looks innocent
    evil.symlink_to(outside)
    # Even though name 'Legal' is fine, resolves outside home → reject
    assert not is_safe_destination(evil, home)
