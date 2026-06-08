"""Direct rendering tests for the Jinja2 prompt templates."""
from app.prompts import render


def test_system_prompt_is_loadable_and_non_empty():
    out = render("selection_system.j2")
    assert "JSON" in out
    assert "chosen_id" in out


def test_choose_by_context_includes_audience_and_candidates():
    out = render(
        "choose_by_context_user.j2",
        context={"audience": {"group": "young_adult"}, "weather": "rain"},
        candidates=[
            {"id": 1, "name": "sunny", "description": "for bright days", "html": "<p>sun</p>"},
            {"id": 2, "name": "rainy", "description": "for wet weather", "html": "<p>rain</p>"},
        ],
    )
    # Keys appear labelled with `| tojson`-quoted values for primitives.
    assert "audience:" in out
    assert "young_adult" in out
    assert "weather:" in out
    assert "\"rain\"" in out
    # Candidates render as before.
    assert "[id=1]" in out
    assert "[id=2]" in out
    assert "<p>sun</p>" in out
    assert "for bright days" in out
    assert "for wet weather" in out


def test_candidates_omits_description_line_when_empty():
    out = render(
        "choose_by_context_user.j2",
        context={"audience": {"group": "x"}},
        candidates=[{"id": 1, "name": "n", "description": "", "html": "<p>x</p>"}],
    )
    assert "description:" not in out


def test_choose_by_context_empty_dict_renders_placeholder():
    out = render(
        "choose_by_context_user.j2",
        context={},
        candidates=[{"id": 1, "name": "x", "description": "", "html": "<p>x</p>"}],
    )
    assert "no context provided" in out


def test_choose_by_context_with_nested_dict():
    """Nested dicts/lists must survive into the prompt as readable JSON."""
    out = render(
        "choose_by_context_user.j2",
        context={"audience": {"group": "kid", "confidence": 0.9}, "tags": ["wet", "cold"]},
        candidates=[{"id": 1, "name": "x", "description": "", "html": "<p>x</p>"}],
    )
    assert "audience:" in out
    # tojson serialises the nested dict so the model sees both keys.
    assert "\"group\"" in out
    assert "\"kid\"" in out
    assert "\"confidence\"" in out
    assert "0.9" in out
    # Lists are preserved.
    assert "tags:" in out
    assert "\"wet\"" in out


def test_choose_by_context_passes_unknown_keys_through():
    out = render(
        "choose_by_context_user.j2",
        context={"foo": "bar", "loudness": "high"},
        candidates=[{"id": 1, "name": "x", "description": "", "html": "<p>x</p>"}],
    )
    assert "foo:" in out
    assert "loudness:" in out


def test_choose_by_image_includes_context_when_present():
    out = render(
        "choose_by_image_user.j2",
        context={"weather": "snowing"},
        candidates=[{"id": 7, "name": "winter", "description": "for cold", "html": "<p>brr</p>"}],
    )
    assert "snowing" in out
    assert "[id=7]" in out
    assert "for cold" in out


def test_choose_by_image_with_no_context():
    out = render(
        "choose_by_image_user.j2",
        context=None,
        candidates=[{"id": 1, "name": "x", "description": "", "html": "<p>x</p>"}],
    )
    assert "no context provided" in out
    assert "[id=1]" in out
