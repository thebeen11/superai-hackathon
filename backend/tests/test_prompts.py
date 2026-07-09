"""Prompt registry + override store — the Agent Console backend."""
from __future__ import annotations

import pytest

from app.prompts import get_prompt, list_prompt_specs, store


@pytest.fixture(autouse=True)
def _isolated_store(monkeypatch):
    """Back the store with an in-memory dict so tests never touch a real database."""
    fake: dict[str, str] = {}
    monkeypatch.setattr(store, "_cache", {})
    monkeypatch.setattr(store, "_loaded", False)
    monkeypatch.setattr("app.db.repository.get_prompt_overrides", lambda: dict(fake))
    monkeypatch.setattr("app.db.repository.set_prompt_override", lambda k, t: fake.__setitem__(k, t))
    monkeypatch.setattr("app.db.repository.delete_prompt_override", lambda k: fake.pop(k, None))
    return fake


def test_all_eleven_prompts_registered_with_unique_keys():
    specs = list_prompt_specs()
    keys = [s.key for s in specs]
    assert len(specs) == 11
    assert len(set(keys)) == 11
    assert "council.chairman" in keys and "insights.context" in keys


def test_default_used_when_no_override():
    assert get_prompt("council.chairman").startswith("You are Winston")


def test_override_takes_effect():
    store.set_override("council.chairman", "BE BRIEF.")
    assert get_prompt("council.chairman") == "BE BRIEF."


def test_reset_restores_default():
    store.set_override("council.chairman", "BE BRIEF.")
    store.delete_override("council.chairman")
    assert get_prompt("council.chairman").startswith("You are Winston")


def test_tracker_placeholder_is_filled():
    assert "'Solar'" in get_prompt("insights.context", tracker="Solar")


def test_taxonomy_placeholder_is_filled():
    out = get_prompt("dataeng.themes", taxonomy=["Solar", "AI"])
    assert "['Solar', 'AI']" in out


def test_unfilled_placeholder_is_left_intact_not_errored():
    # A user who removes the value (or the caller omits it) gets the literal token back,
    # never a KeyError.
    store.set_override("insights.context", "Score against {tracker} only.")
    assert get_prompt("insights.context") == "Score against {tracker} only."


def test_user_supplied_braces_are_preserved():
    # Prompt text may contain literal braces (e.g. a JSON example); only declared
    # placeholders are substituted, everything else is passed through verbatim.
    store.set_override("dataeng.redact", 'Reply with {"clean_text": "..."}')
    assert get_prompt("dataeng.redact") == 'Reply with {"clean_text": "..."}'


def test_override_survives_db_failure_via_in_memory_cache(monkeypatch):
    # If the DB write raises, the override still applies within the running process.
    def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.db.repository.set_prompt_override", boom)
    store.set_override("council.analyst", "IN MEMORY ONLY")
    assert get_prompt("council.analyst") == "IN MEMORY ONLY"
