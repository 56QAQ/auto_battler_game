"""CLI commands run end to end on the bundled examples."""

import json

from hsrsim.cli import main


def test_run_and_json(tmp_path, capsys):
    out = tmp_path / "rep.json"
    main(["run", "examples/acheron_boss.yaml", "--runs", "2", "--json", str(out)])
    text = capsys.readouterr().out
    assert "Total DMG" in text and "2 runs" in text
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 2 and data[0]["total"] > 0


def test_stats(capsys):
    main(["stats", "examples/firefly_break_aoe.yaml"])
    assert "Break Effect" in capsys.readouterr().out


def test_trace(capsys):
    main(["trace", "examples/acheron_boss.yaml", "--character", "Acheron", "--limit", "5", "--cycles", "2"])
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 6 and "Acheron" in lines[1]


def test_endgame_preset(capsys):
    main(["run", "examples/moc12_elation.yaml", "--runs", "1"])
    assert "Memory of Chaos" in capsys.readouterr().out


def test_list(capsys):
    main(["list", "relics", "--implemented"])
    assert "Genius of Brilliant Stars" in capsys.readouterr().out
