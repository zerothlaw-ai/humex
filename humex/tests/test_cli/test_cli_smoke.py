"""Smoke tests for the humex CLI — verifies that each subcommand is wired up,
shows ``--help``, and exits cleanly. End-to-end conversion / evaluation tests
live alongside the corresponding converter and metric fixtures.
"""

from click.testing import CliRunner

from humex.cli.main import cli


def test_root_help_lists_subcommands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    out = result.output
    for sub in ("convert", "evaluate", "lane-map", "package"):
        assert sub in out, f"subcommand missing from --help: {sub}"


def test_version_flag():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "humex" in result.output.lower()


def test_convert_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["convert", "--help"])
    assert result.exit_code == 0
    assert "PATH" in result.output


def test_evaluate_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["evaluate", "--help"])
    assert result.exit_code == 0
    assert "--metric" in result.output


def test_lane_map_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["lane-map", "--help"])
    assert result.exit_code == 0
    assert "scenario.pb" in result.output.lower() or "SCENARIO_DIR" in result.output


def test_package_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["package", "--help"])
    assert result.exit_code == 0
    assert ".hpkg" in result.output
