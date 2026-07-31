import sqlite3

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from app import workflow
from app.models import (
    PodcastScriptRequest,
    PodcastScriptResponse,
    PodcastWorkflowApprovalRequest,
)


def make_script(label: str) -> PodcastScriptResponse:

    return PodcastScriptResponse(
        title=f"Episode {label}",
        segments=[
            {"speaker": "host", "text": f"Host {label}"},
            {"speaker": "guest", "text": f"Guest {label}"},
        ],
    )


def initial_state() -> dict[str, object]:

    return {
        "source_text": "SQLite runs in the application process.",
        "format": "interview",
        "duration": "short",
        "facts": [],
        "issues": [],
        "revision_count": 0,
        "status": "extracting",
    }


def test_workflow_bounds_revisions_and_resumes_human_approval():

    calls = {"evaluate": 0, "revise": 0}

    def extract_facts(_state):
        return ["SQLite runs in the application process."]

    def draft_script(_state):
        return make_script("draft")

    def evaluate_script(_state):
        calls["evaluate"] += 1
        return ["The location claim needs verification."]

    def revise_script(_state):
        calls["revise"] += 1
        return make_script(f"revision-{calls['revise']}")

    graph = workflow.build_podcast_workflow(
        InMemorySaver(),
        extract_facts=extract_facts,
        draft_script=draft_script,
        evaluate_script=evaluate_script,
        revise_script=revise_script,
    )

    config = {"configurable": {"thread_id": "bounded-loop"}}

    result = graph.invoke(initial_state(), config=config)

    assert calls == {"evaluate": 3, "revise": 2}
    assert result["revision_count"] == 2
    assert result["status"] == "awaiting_review"
    assert result["script"]["title"] == "Episode revision-2"
    assert result["issues"] == ["The location claim needs verification."]
    assert "__interrupt__" in result

    graph.invoke(
        Command(
            resume={
                "script": make_script("human-approved").model_dump(mode="json"),
                "language_code": "a",
                "host_voice": "af_heart",
                "guest_voice": "af_bella",
            }
        ),
        config=config,
    )

    approved_state = graph.get_state(config).values

    assert approved_state["status"] == "approved"
    assert approved_state["script"]["title"] == "Episode human-approved"
    assert approved_state["host_voice"] == "af_heart"
    assert approved_state["guest_voice"] == "af_bella"


def test_workflow_skips_revision_when_source_check_passes():

    def unexpected_revision(_state):
        raise AssertionError("Clean scripts must not enter the revision node")

    graph = workflow.build_podcast_workflow(
        InMemorySaver(),
        extract_facts=lambda _state: ["One supported fact."],
        draft_script=lambda _state: make_script("clean"),
        evaluate_script=lambda _state: [],
        revise_script=unexpected_revision,
    )
    config = {"configurable": {"thread_id": "clean-review"}}

    result = graph.invoke(initial_state(), config=config)

    assert result["status"] == "awaiting_review"
    assert result["revision_count"] == 0
    assert result["issues"] == []


def test_workflow_service_starts_approves_and_links_audio(monkeypatch):

    graph = workflow.build_podcast_workflow(
        InMemorySaver(),
        extract_facts=lambda _state: ["SQLite is embedded."],
        draft_script=lambda _state: make_script("service"),
        evaluate_script=lambda _state: [],
        revise_script=lambda _state: make_script("unused"),
    )

    monkeypatch.setattr(workflow, "_workflow_graph", graph)

    created = workflow.start_podcast_workflow(
        PodcastScriptRequest(
            text="SQLite is embedded.",
            format="interview",
            duration="short",
        )
    )

    assert created.status == "awaiting_review"
    assert created.facts == ["SQLite is embedded."]
    assert created.script.title == "Episode service"

    approved = workflow.approve_podcast_workflow(
        created.workflow_id,
        PodcastWorkflowApprovalRequest(
            script=make_script("approved"),
            language_code="a",
            host_voice="af_heart",
            guest_voice="af_bella",
        ),
    )

    linked = workflow.link_podcast_audio_job(
        created.workflow_id,
        created.workflow_id,
    )

    assert approved.status == "approved"
    assert linked.status == "queued"
    assert linked.audio_job_id == created.workflow_id
    recovered = workflow.get_podcast_workflow(created.workflow_id)
    assert recovered.script.title == "Episode approved"


def test_workflow_recovers_interrupt_from_new_sqlite_connection(tmp_path):

    node_options = {
        "extract_facts": lambda _state: ["SQLite is embedded."],
        "draft_script": lambda _state: make_script("persistent"),
        "evaluate_script": lambda _state: [],
        "revise_script": lambda _state: make_script("unused"),
    }

    database_path = tmp_path / "podcast_workflows.db"
    config = {"configurable": {"thread_id": "restart-safe"}}

    first_connection = sqlite3.connect(database_path, check_same_thread=False)
    first_saver = SqliteSaver(first_connection)
    first_saver.setup()
    first_graph = workflow.build_podcast_workflow(first_saver, **node_options)
    first_graph.invoke(initial_state(), config=config)
    assert first_graph.get_state(config).values["status"] == "awaiting_review"

    first_connection.close()

    second_connection = sqlite3.connect(database_path, check_same_thread=False)
    second_saver = SqliteSaver(second_connection)
    second_saver.setup()
    second_graph = workflow.build_podcast_workflow(second_saver, **node_options)

    recovered = second_graph.get_state(config).values
    assert recovered["status"] == "awaiting_review"
    assert recovered["script"]["title"] == "Episode persistent"

    second_graph.invoke(
        Command(
            resume={
                "script": make_script("after-restart").model_dump(mode="json"),
                "language_code": "a",
                "host_voice": "af_heart",
                "guest_voice": "af_bella",
            }
        ),
        config=config,
    )

    assert second_graph.get_state(config).values["script"]["title"] == (
        "Episode after-restart"
    )
    second_connection.close()
