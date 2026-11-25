"""
@file tests/agent_engine/test_interface.py
@description The interface of the app (ADR-034): its language, the language
of the chosen voice, the notice when they differ, the context Aurora gets
about the app, and Aurora changing the language in a real run.
"""

from __future__ import annotations

import pytest

from app.agent_engine.application import AgentEngine, NativeAgentWorker
from app.agent_engine.runtime import AgentRuntime
from app.core import interface
from app.core.runtime_config import config_value, replace_stored
from app.core.security import Principal, RoleEnum
from app.skills import interface_skill


@pytest.fixture(autouse=True)
def clean_settings():
    replace_stored({})
    interface._elevenlabs_languages.clear()
    yield
    replace_stored({})
    interface._elevenlabs_languages.clear()


def test_english_by_default_and_the_voice_language_follows_the_voice():
    state = interface.interface_state()

    assert state["language"] == "en"
    assert state["voice_language_warning"] is True
    # The default Piper voice is it_IT-paola-medium.
    assert state["voice"]["language"] == "it"

    replace_stored({"AEHUB_TTS_VOICE": "en_GB-alba-medium", "AEHUB_UI_LANGUAGE": "it"})
    assert interface.voice_language() == "en"
    assert interface.interface_language() == "it"


def test_an_elevenlabs_voice_has_the_language_of_its_labels():
    replace_stored({"AEHUB_TTS_ENGINE": "elevenlabs", "AEHUB_ELEVENLABS_VOICE": "abcdefgh12"})
    assert interface.voice_language() is None

    interface.remember_elevenlabs_languages(
        [
            {"voice_id": "abcdefgh12", "labels": {"language": "Italian"}},
            {"voice_id": "zzzzzzzz99", "labels": {"accent": "american"}},
        ]
    )
    assert interface.voice_language() == "it"


def test_the_settings_are_validated():
    from app.core.settings_service import SettingsValidationError, validate_changes

    assert validate_changes({"AEHUB_UI_LANGUAGE": "it", "AEHUB_VOICE_LANGUAGE_WARNING": "off"})
    for name, bad in (("AEHUB_UI_LANGUAGE", "fr"), ("AEHUB_VOICE_LANGUAGE_WARNING", "maybe")):
        with pytest.raises(SettingsValidationError):
            validate_changes({name: bad})


def test_aurora_knows_the_app_she_runs_in():
    # The test environment turns voice off; here it is on.
    replace_stored({"AEHUB_VOICE": "local"})
    context = interface.app_context()

    assert "ÆHub" in context
    assert "Interface: English." in context
    assert "Voice: Italian." in context
    assert "set_interface_language" in context

    replace_stored({"AEHUB_UI_LANGUAGE": "it", "AEHUB_VOICE": "off", "AEHUB_VOICE_LANGUAGE_WARNING": "off"})
    context = interface.app_context()
    assert "Interface: Italian." in context
    assert "Voice: off." in context
    assert "Voice language notice: off." in context

    worker = NativeAgentWorker(model_provider=None, system_prompt="Fixed contract.")
    assert worker.full_system_prompt().startswith("Fixed contract.\n\nYou are Aurora")


def test_the_interface_tools_are_low_risk_and_findable():
    metadata = interface_skill.get_skill().get_tool_metadata()

    assert set(metadata) == {"set_interface_language", "set_voice_language_warning"}
    assert all(entry.risk_level.value == "low" and not entry.requires_approval for entry in metadata.values())
    assert metadata["set_interface_language"].input_schema["properties"]["language"]["enum"] == ["en", "it"]


async def test_aurora_changes_the_language_in_a_run(agent_infrastructure, fake_model, db_session_factory):
    agent_infrastructure.use_skills(interface_skill.get_skill())

    engine = AgentEngine(
        model_provider=fake_model.adapter(
            [
                fake_model.function_call("call_lang", "set_interface_language", {"language": "it"}),
                fake_model.function_call("call_notice", "set_voice_language_warning", {"enabled": False}),
                fake_model.text("Fatto: l'interfaccia è in italiano."),
            ]
        ),
        checker_provider=fake_model.checker([fake_model.accept()]),
        runtime=AgentRuntime(),
    )
    owner = Principal(id="owner", role=RoleEnum.ADMIN, workspace_id="workspace-ui")

    result = await engine.run(session_id="session-ui", task="Metti l'app in italiano.", principal=owner)

    assert result["messages"][0].content == "Fatto: l'interfaccia è in italiano."
    assert config_value("AEHUB_UI_LANGUAGE") == "it"
    assert config_value("AEHUB_VOICE_LANGUAGE_WARNING") == "off"

    # Saved and audited like a change from IMPOSTAZIONI.
    from app.domain.models.audit import AuditLog
    from app.domain.models.settings import AppSetting

    with db_session_factory() as db:
        assert db.get(AppSetting, "AEHUB_UI_LANGUAGE").value == "it"
        assert db.query(AuditLog).filter(AuditLog.tool_name == "settings.update").count() == 2

    changed = [data for _, event_type, data in agent_infrastructure.published if event_type == "interface.changed"]
    assert changed[-1]["language"] == "it"
    assert changed[-1]["voice_language_warning"] is False

    # The model's instructions carry the app context.
    assert "You are Aurora" in engine.worker.full_system_prompt()


async def test_an_unknown_language_is_refused():
    with pytest.raises(ValueError, match="en, it"):
        await interface_skill.set_interface_language("fr")
