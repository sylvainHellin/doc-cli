"""CLI tests for -o/--output on parse and ocr (pipeline stubbed, no engines)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import doc_cli.pipeline
from doc_cli.cli import main

BIG = "x" * 40_000


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    """Default config and a stubbed pipeline; returns a setter for the fake Markdown."""
    monkeypatch.setenv("DOC_CONFIG", str(tmp_path / "missing-config.json"))
    state = {"text": BIG, "calls": []}

    def fake_parse(file, engine, config):
        state["calls"].append(("parse", file))
        return {"markdown": state["text"], "engine": "fake"}

    def fake_ocr_files(files, engine, config):
        state["calls"].append(("ocr", [str(f) for f in files]))
        return {"markdown": state["text"], "engine": "fake"}

    monkeypatch.setattr(doc_cli.pipeline, "parse", fake_parse)
    monkeypatch.setattr(doc_cli.pipeline, "ocr_files", fake_ocr_files)
    return state


def test_parse_large_output_to_file(cli_env, tmp_path, capsys):
    out = tmp_path / "out.md"
    rc = main(["parse", "x.pdf", "-o", str(out)])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == ""
    assert out.read_text(encoding="utf-8") == BIG + "\n"
    assert captured.err == f"wrote {len(BIG)} chars to {out}\n"


def test_ocr_to_file(cli_env, tmp_path, capsys):
    out = tmp_path / "out.md"
    rc = main(["ocr", "a.png", "b.png", "--output", str(out)])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == ""
    assert out.read_text(encoding="utf-8") == BIG + "\n"
    assert cli_env["calls"] == [("ocr", ["a.png", "b.png"])]


def test_json_to_file(cli_env, tmp_path, capsys):
    out = tmp_path / "out.json"
    rc = main(["--json", "parse", "x.pdf", "-o", str(out)])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == ""
    assert json.loads(out.read_text(encoding="utf-8")) == {"markdown": BIG, "engine": "fake"}


def test_dash_prints_full_output_without_spill(cli_env, capsys):
    rc = main(["parse", "x.pdf", "-o", "-"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == BIG + "\n"
    assert captured.err == ""


def test_missing_parent_dirs_created(cli_env, tmp_path, capsys):
    out = tmp_path / "a" / "b" / "out.md"
    rc = main(["parse", "x.pdf", "-o", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8") == BIG + "\n"


def test_overwrites_existing_file(cli_env, tmp_path, capsys):
    out = tmp_path / "out.md"
    out.write_text("old content that should vanish\n" * 10, encoding="utf-8")
    cli_env["text"] = "new"
    rc = main(["parse", "x.pdf", "-o", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8") == "new\n"


def test_unwritable_target_is_directory(cli_env, tmp_path, capsys):
    target = tmp_path / "adir"
    target.mkdir()
    rc = main(["parse", "x.pdf", "-o", str(target)])
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.err.startswith("error: cannot write")
    assert "Traceback" not in captured.err
    assert captured.out == ""


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_target_read_only_dir(cli_env, tmp_path, capsys):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        rc = main(["parse", "x.pdf", "-o", str(ro / "out.md")])
    finally:
        ro.chmod(0o700)
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.err.startswith("error: cannot write")
    assert "Traceback" not in captured.err


def test_default_large_output_spills(cli_env, capsys):
    rc = main(["parse", "x.pdf"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err.startswith(f"[output {len(BIG)} chars spilled to]")
    spill_path = Path(captured.out.strip())
    assert spill_path.read_text(encoding="utf-8") == BIG


def test_default_small_output_printed(cli_env, capsys):
    cli_env["text"] = "small"
    rc = main(["parse", "x.pdf"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == "small\n"
    assert captured.err == ""


def test_inspect_rejects_output_flag(cli_env, tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["inspect", "x.pdf", "-o", str(tmp_path / "out.md")])
    assert exc.value.code == 2
