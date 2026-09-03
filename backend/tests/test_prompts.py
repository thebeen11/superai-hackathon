"""Prompt registry + override store — the Agent Console backend."""
from __future__ import annotations

import pytest

from app.prompts import get_prompt, identity, list_prompt_specs, list_skill_specs, store


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


@pytest.fixture
def _no_layers(monkeypatch):
    """Run with identity composition off — `get_prompt` returns the bare task text."""
    from app.config import settings

    monkeypatch.setattr(settings, "agent_identity_layers", False)


def test_all_skill_prompts_registered_with_unique_keys():
    specs = list_skill_specs()
    keys = [s.key for s in specs]
    assert len(specs) == 19
    assert len(set(keys)) == len(specs)
    assert "council.chairman" in keys and "insights.context" in keys
    assert "council.thematic" in keys
    # the single-ticker chamber runs on its own prompts, tunable without touching the
    # council-wide debate
    assert "council.debate.ticker.bull" in keys and "council.debate.ticker.bear" in keys
    assert "council.chairman.ticker" in keys
    assert "council.macro" in keys and "insights.watchlist_match" in keys
    # the concept trackers' direction is its own graded call, tunable on its own
    assert "council.themes" in keys
    assert "council.macro_backfill" in keys   # the Macro Analyst's second pass
    assert all(s.layer == "skill" and s.agent for s in specs)


def test_catalogue_adds_identity_layers_with_unique_keys():
    specs = list_prompt_specs()
    keys = [s.key for s in specs]
    assert len(set(keys)) == len(keys)
    # every skill + soul + rules + 6 mental models + one personality per agent.
    assert len(specs) == len(list_skill_specs()) + 2 + 6 + len(identity.AGENTS)
    layers = {s.layer for s in specs}
    assert layers == {"skill", "soul", "rules", "mental_model", "personality"}


def test_default_used_when_no_override(_no_layers):
    assert get_prompt("council.chairman").startswith("You are Winston")


def test_citing_agents_all_state_the_index_citation_contract(_no_layers):
    """Every agent that emits evidence must ask for excerpt indices, not free-text URLs.

    Grounding maps `source_index` back to a real source; a prompt that forgets to ask for
    it silently produces un-anchored claims (which is exactly how the Chairman used to
    behave), so the contract is asserted rather than left to review.
    """
    for key in ("council.chairman", "council.analyst", "council.macro", "council.thematic"):
        text = get_prompt(key).lower()
        assert "index" in text or "indices" in text, f"{key} does not ask for a source index"
    chairman = get_prompt("council.chairman")
    assert "SOURCES" in chairman
    assert "indicator, briefing bullet and prediction" in chairman
    # Baskets moved to the weekly thematic prompt, which carries the same contract.
    thematic = get_prompt("council.thematic")
    assert "SOURCES" in thematic
    assert "every basket takes an 'evidence' list" in thematic


def test_override_takes_effect(_no_layers):
    store.set_override("council.chairman", "BE BRIEF.")
    assert get_prompt("council.chairman") == "BE BRIEF."


def test_reset_restores_default(_no_layers):
    store.set_override("council.chairman", "BE BRIEF.")
    store.delete_override("council.chairman")
    assert get_prompt("council.chairman").startswith("You are Winston")


def test_tracker_placeholder_is_filled():
    assert "'Solar'" in get_prompt("insights.context", tracker="Solar")


def test_taxonomy_placeholder_is_filled():
    out = get_prompt("dataeng.themes", taxonomy=["Solar", "AI"])
    assert "['Solar', 'AI']" in out


def test_unfilled_placeholder_is_left_intact_not_errored(_no_layers):
    # A user who removes the value (or the caller omits it) gets the literal token back,
    # never a KeyError.
    store.set_override("insights.context", "Score against {tracker} only.")
    assert get_prompt("insights.context") == "Score against {tracker} only."


def test_user_supplied_braces_are_preserved(_no_layers):
    # Prompt text may contain literal braces (e.g. a JSON example); only declared
    # placeholders are substituted, everything else is passed through verbatim.
    store.set_override("dataeng.redact", 'Reply with {"clean_text": "..."}')
    assert get_prompt("dataeng.redact") == 'Reply with {"clean_text": "..."}'


def test_override_survives_db_failure_via_in_memory_cache(monkeypatch, _no_layers):
    # If the DB write raises, the override still applies within the running process.
    def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.db.repository.set_prompt_override", boom)
    store.set_override("council.analyst", "IN MEMORY ONLY")
    assert get_prompt("council.analyst") == "IN MEMORY ONLY"


# --- Identity layers: soul, rules, mental models, personality ---------------


def _headings(text: str) -> list[str]:
    return [line[3:] for line in text.splitlines() if line.startswith("## ")]


def test_composed_prompt_stacks_layers_in_order_and_keeps_the_task():
    text = get_prompt("council.chairman")
    heads = _headings(text)
    assert heads == ["SOUL", "RULES", "MENTAL MODELS", "PERSONALITY", "TASK — Winston · Chairman"]
    assert "You are Winston" in text          # the original task prompt survives intact
    assert text.rstrip().endswith("the task wins.")


def test_layers_off_is_byte_identical_to_the_bare_task_prompt(monkeypatch):
    from app.config import settings
    from app.prompts.registry import list_skill_specs as skills

    composed = get_prompt("council.chairman")
    monkeypatch.setattr(settings, "agent_identity_layers", False)
    bare = get_prompt("council.chairman")
    assert bare == next(s for s in skills() if s.key == "council.chairman").default_template
    assert bare != composed


def test_editing_the_soul_changes_every_agent():
    store.set_override(identity.SOUL_KEY, "WE ARE THE MACHINE.")
    for key in ("council.chairman", "dataeng.redact", "discovery.refine"):
        assert "WE ARE THE MACHINE." in get_prompt(key)


def test_personality_is_per_agent():
    assert "Chairman's voice" in get_prompt("council.chairman")
    assert "Chairman's voice" not in get_prompt("council.debate.bull")
    assert "growth PM" in get_prompt("council.debate.bull")


def test_desks_share_a_task_prompt_but_not_a_voice():
    tmt = get_prompt("council.analyst", agent="andie-tech")
    physical = get_prompt("council.analyst", agent="andie-physical")
    assert "You are Andie, a buy-side sector analyst" in tmt
    assert "You are Andie, a buy-side sector analyst" in physical
    assert "supply chains" in tmt and "supply chains" not in physical
    assert "grid load" in physical


def test_mental_models_follow_the_agent_assignment():
    # Winston runs Inversion by default; Timo does not.
    assert "Inversion:" in get_prompt("council.chairman")
    assert "Inversion:" not in get_prompt("dataeng.redact")
    identity.set_mental_models("winston", ["mental.pareto_8020"])
    winston = get_prompt("council.chairman")
    assert "Inversion:" not in winston and "80/20 (Pareto):" in winston


def test_mental_model_assignment_round_trips_and_ignores_unknown_keys():
    kept = identity.set_mental_models("timo", ["mental.inversion", "not.a.framework"])
    assert kept == ["mental.inversion"]
    assert identity.mental_models_for("timo") == ["mental.inversion"]
    # Assignments are ordered by the library, not by click order.
    identity.set_mental_models("timo", ["mental.falsification", "mental.first_principles"])
    assert identity.mental_models_for("timo") == ["mental.first_principles", "mental.falsification"]
    assert identity.reset_mental_models("timo") == list(identity.get_agent("timo").mental_models)


def test_empty_assignment_drops_the_mental_models_section():
    identity.set_mental_models("winston", [])
    assert "MENTAL MODELS" not in _headings(get_prompt("council.chairman"))


def test_corrupt_assignment_falls_back_to_defaults():
    store.set_override("assign.mental_models.winston", "{not json")
    assert identity.mental_models_for("winston") == list(identity.get_agent("winston").mental_models)


def test_placeholders_still_fill_inside_a_composed_prompt():
    out = get_prompt("insights.context", tracker="Solar")
    assert "SOUL" in out and "'Solar'" in out and "{tracker}" not in out


def test_editing_a_mental_model_reaches_every_agent_that_runs_it():
    store.set_override("mental.base_rates", "COUNT, DO NOT FEEL.")
    assert "COUNT, DO NOT FEEL." in get_prompt("council.chairman")   # runs base rates
    assert "COUNT, DO NOT FEEL." not in get_prompt("dataeng.redact")  # does not


def test_shared_desk_skill_is_listed_for_every_desk_that_runs_it():
    from app.council.analyst import DESK_AGENTS

    for agent_id in DESK_AGENTS.values():
        assert identity.skills_for(agent_id) == ["council.analyst"]
    # The console's roster and the runtime router must not drift apart.
    assert set(DESK_AGENTS.values()) == set(identity.agents_running(
        next(s for s in list_skill_specs() if s.key == "council.analyst")
    ))


def test_tool_only_agents_have_no_skills():
    assert identity.skills_for("wilfred-video") == []


def test_identity_layers_are_editable_like_any_other_prompt():
    keys = {s.key for s in list_prompt_specs()}
    assert {identity.SOUL_KEY, identity.RULES_KEY, "mental.inversion"} <= keys
    assert identity.personality_key("winston") in keys


# --- Agent Console save guard ------------------------------------------------------


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app import main

    return TestClient(main.app)


def test_saving_a_prompt_without_its_placeholder_is_rejected(client, _isolated_store):
    body = {"text": "You are the Macro Analyst. Grade the fixed checklist below."}
    r = client.put("/api/prompts/council.macro", json=body)

    assert r.status_code == 400
    assert "{signposts}" in r.json()["detail"]
    # The refusal must not half-apply: the old text is still what the agent runs on.
    assert store.get_override("council.macro") is None


def test_saving_a_prompt_that_keeps_its_placeholder_succeeds(client, _isolated_store):
    text = "Grade only this checklist.\n\nCHECKLIST:\n{signposts}"
    r = client.put("/api/prompts/council.macro", json={"text": text})

    assert r.status_code == 200
    assert r.json()["is_overridden"] is True
    assert store.get_override("council.macro") == text


def test_the_guard_covers_every_placeholder_prompt(client, _isolated_store):
    # Not a macro special case — the same silent failure exists for each of these.
    for key in ("dataeng.labels", "dataeng.themes", "insights.watchlist_match"):
        r = client.put("/api/prompts/" + key, json={"text": "no placeholders here"})
        assert r.status_code == 400, key
        assert store.get_override(key) is None, key


def test_a_placeholderless_prompt_still_saves_anything(client, _isolated_store):
    r = client.put("/api/prompts/council.chairman", json={"text": "Be brief."})
    assert r.status_code == 200
    assert store.get_override("council.chairman") == "Be brief."
