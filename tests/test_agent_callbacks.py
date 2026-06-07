from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_override_model_injects_tracking_args(
    active_project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kady_agent import agent

    original_args = dict(agent._LITELLM_MODEL._additional_args)
    try:
        agent._LITELLM_MODEL._additional_args.clear()
        request = SimpleNamespace(model="original")
        context = SimpleNamespace(
            state={
                "_model": "venice/minimax-m3",
                "_sessionId": "session",
                "_turnId": "turn",
            }
        )

        assert agent._override_model(context, request) is None

        assert request.model == "openai/minimax-m3"
        args = agent._LITELLM_MODEL._additional_args
        assert args["extra_headers"]["X-Kady-Role"] == "orchestrator"
        assert args["extra_headers"]["X-Kady-Session-Id"] == "session"
        assert args["extra_headers"]["X-Kady-Project"] == active_project
        assert args["metadata"]["kady_turn_id"] == "turn"
    finally:
        agent._LITELLM_MODEL._additional_args.clear()
        agent._LITELLM_MODEL._additional_args.update(original_args)


async def test_open_and_close_turn_manifest_callbacks(
    active_project: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kady_agent import agent, runtime

    monkeypatch.setattr(runtime, "_git_sha", lambda: "sha")
    monkeypatch.setattr(runtime, "_node_version", lambda: "node")
    monkeypatch.setattr(runtime, "_gemini_cli_version", lambda: "gemini")
    monkeypatch.setattr(runtime, "_litellm_config_sha", lambda: "litellm")

    user_content = SimpleNamespace(parts=[SimpleNamespace(text="hello"), SimpleNamespace(text=" world")])
    invocation = SimpleNamespace(session=SimpleNamespace(id="session-cb"), user_content=user_content)
    context = SimpleNamespace(
        state={"_model": "venice/minimax-m3", "_expertModel": "venice/qwen3-5-9b"},
        _invocation_context=invocation,
    )

    assert await agent._open_turn_manifest(context) is None
    assert context.state["_turnId"]
    assert context.state["_sessionId"] == "session-cb"

    context.state["final_output"] = "assistant output"
    assert await agent._close_turn_manifest(context) is None

    manifest = runtime.read_manifest("session-cb", context.state["_turnId"])
    assert manifest["output"]["assistantTextPreview"] == "assistant output"


def test_orchestrator_cost_logger_records(active_project: str) -> None:
    from kady_agent import agent, runtime

    logger = agent._OrchestratorCostLogger()
    tags = runtime.build_tracking_metadata(
        role="orchestrator",
        project_id=active_project,
        session_id="session-cost",
        turn_id="turn-cost",
    )
    kwargs = {
        "model": "openai/minimax-m3",
        "litellm_params": {"metadata": tags},
    }
    response = {"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_cost": 0.03}}

    logger._record(kwargs, response)

    summary = runtime.read_costs("session-cost", project_id=active_project)
    assert summary["orchestratorUsd"] == 0.03
    assert summary["entries"][0]["model"] == "openai/minimax-m3"
