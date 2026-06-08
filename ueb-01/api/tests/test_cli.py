"""Smoke tests for the `digsig` CLI — verify wiring of pool + content commands.

CLI commands use ``asyncio.run`` internally, so these tests stay sync; the
autouse fixture in conftest is sync too. State is verified by invoking
further CLI commands, not by reaching into the database directly.
"""
import re

from typer.testing import CliRunner

from app.cli import cli

runner = CliRunner()


def _created_id(output: str) -> int:
    """Parse 'created pool #N: ...' (or 'created content #N ...') from CLI output."""
    m = re.search(r"#(\d+)", output)
    assert m, f"no id in output: {output!r}"
    return int(m.group(1))


def test_pool_create_and_list():
    result = runner.invoke(cli, ["pool", "create", "kids", "--description", "for kids"])
    assert result.exit_code == 0, result.output
    assert "created pool" in result.output

    result = runner.invoke(cli, ["pool", "list"])
    assert result.exit_code == 0
    assert "kids" in result.output


def test_content_add_writes_html(tmp_path):
    create = runner.invoke(cli, ["pool", "create", "adults"])
    pool_id = _created_id(create.output)

    html_file = tmp_path / "snippet.html"
    html_file.write_text("<p>Welcome adult</p>", encoding="utf-8")

    result = runner.invoke(
        cli,
        ["content", "add", str(pool_id), "--name", "welcome", "--html-file", str(html_file)],
    )
    assert result.exit_code == 0, result.output
    assert "added content" in result.output

    listing = runner.invoke(cli, ["content", "list", str(pool_id)])
    assert listing.exit_code == 0
    assert "welcome" in listing.output


def test_pool_show_includes_contents(tmp_path):
    create = runner.invoke(cli, ["pool", "create", "weather"])
    pool_id = _created_id(create.output)
    html_file = tmp_path / "rainy.html"
    html_file.write_text("<p>rain</p>", encoding="utf-8")
    runner.invoke(
        cli,
        ["content", "add", str(pool_id), "--name", "rainy", "--html-file", str(html_file)],
    )

    result = runner.invoke(cli, ["pool", "show", str(pool_id)])
    assert result.exit_code == 0, result.output
    assert "weather" in result.output
    assert "rainy" in result.output


def test_pool_delete_missing_returns_error_exit():
    result = runner.invoke(cli, ["pool", "delete", "9999"])
    assert result.exit_code != 0


def test_seed_bakery_creates_pool_with_six_contents():
    result = runner.invoke(cli, ["seed", "bakery"])
    assert result.exit_code == 0, result.output
    assert "created pool" in result.output
    # Six fixture files, six 'added content' lines.
    assert result.output.count("added content") == 6


def test_seed_bakery_refuses_when_pool_exists():
    runner.invoke(cli, ["seed", "bakery"])
    again = runner.invoke(cli, ["seed", "bakery"])
    assert again.exit_code != 0
    assert "already exists" in again.output


def test_seed_bakery_reset_replaces_pool():
    runner.invoke(cli, ["seed", "bakery"])
    result = runner.invoke(cli, ["seed", "bakery", "--reset"])
    assert result.exit_code == 0, result.output
    assert "deleted existing pool" in result.output
    assert result.output.count("added content") == 6
