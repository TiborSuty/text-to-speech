import atexit

import os

import sqlite3

from threading import Lock

from typing import Callable, TypedDict

from uuid import uuid4


from langgraph.checkpoint.sqlite import SqliteSaver

from langgraph.graph import END, START, StateGraph

from langgraph.types import Command, interrupt

from langchain_ollama import ChatOllama

from pydantic import BaseModel, Field, field_validator


from app.models import (
    PodcastScriptRequest,
    PodcastScriptResponse,
    PodcastWorkflowApprovalRequest,
    PodcastWorkflowResponse,
)

from app.text import OLLAMA_BASE_URL, OLLAMA_MODEL, PODCAST_DURATION_GUIDES


MAX_PODCAST_REVISIONS = 2

PODCAST_WORKFLOW_DB_PATH = os.getenv(
    "PODCAST_WORKFLOW_DB_PATH",
    "data/podcast_workflows.db",
)


class PodcastWorkflowState(TypedDict, total=False):
    source_text: str

    format: str

    duration: str

    facts: list[str]

    script: dict[str, object]

    issues: list[str]

    revision_count: int

    status: str

    language_code: str

    host_voice: str

    guest_voice: str

    audio_format: str

    audio_job_id: str


class ExtractedPodcastFacts(BaseModel):
    facts: list[str] = Field(min_length=1, max_length=24)

    @field_validator("facts")
    @classmethod
    def clean_facts(cls, values: list[str]) -> list[str]:

        cleaned_values = [value.strip() for value in values if value.strip()]

        if not cleaned_values:
            raise ValueError("At least one source fact is required")

        return cleaned_values


class PodcastGroundingReview(BaseModel):
    issues: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("issues")
    @classmethod
    def clean_issues(cls, values: list[str]) -> list[str]:

        return [value.strip() for value in values if value.strip()]


ExtractFacts = Callable[[PodcastWorkflowState], list[str]]

GenerateScript = Callable[[PodcastWorkflowState], PodcastScriptResponse]

EvaluateScript = Callable[[PodcastWorkflowState], list[str]]


class PodcastWorkflowError(RuntimeError):
    pass


class PodcastWorkflowNotFoundError(PodcastWorkflowError):
    pass


def _structured_model(schema: type[BaseModel]) -> object:

    model = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.1,
    )

    return model.with_structured_output(schema, method="json_schema")


def extract_source_facts(state: PodcastWorkflowState) -> list[str]:

    prompt = f"""
Extract the important, independently checkable facts from the source below.
Preserve names, numbers, dates, qualifications, and causal relationships exactly.
Do not infer or add information. Return facts in the source language.

Source:
{state["source_text"]}
"""

    try:
        result = ExtractedPodcastFacts.model_validate(
            _structured_model(ExtractedPodcastFacts).invoke(prompt)
        )

    except Exception as exc:
        raise PodcastWorkflowError(
            f"Could not extract source facts. Make sure Ollama is running and {OLLAMA_MODEL} is installed."
        ) from exc

    return result.facts


def draft_grounded_script(state: PodcastWorkflowState) -> PodcastScriptResponse:

    fact_checklist = "\n".join(f"- {fact}" for fact in state["facts"])

    prompt = f"""
You are an experienced podcast editor. Create an accurate, natural spoken script.

Format: {state["format"]}
Length target: {PODCAST_DURATION_GUIDES[state["duration"]]}

Rules:
- Use only facts supported by the source and checklist.
- Preserve important names, numbers, dates, and qualifications.
- Write the title and spoken turns in the source language.
- Use only speaker labels "host" and "guest".
- For narration, use only "host".
- Do not add stage directions, markdown, citations, or sound effects.

Extracted fact checklist:
{fact_checklist}

Full source:
{state["source_text"]}
"""

    try:
        script = PodcastScriptResponse.model_validate(
            _structured_model(PodcastScriptResponse).invoke(prompt)
        )

    except Exception as exc:
        raise PodcastWorkflowError(
            f"Could not draft a grounded podcast. Make sure Ollama is running and {OLLAMA_MODEL} is installed."
        ) from exc

    if state["format"] == "narration":
        script = script.model_copy(
            update={
                "segments": [
                    segment.model_copy(update={"speaker": "host"})
                    for segment in script.segments
                ]
            }
        )

    return script


def evaluate_script_grounding(state: PodcastWorkflowState) -> list[str]:

    script_json = PodcastScriptResponse.model_validate(state["script"]).model_dump_json(
        indent=2
    )

    fact_checklist = "\n".join(f"- {fact}" for fact in state["facts"])

    prompt = f"""
Audit this podcast script against the source. Report only concrete factual problems:
unsupported claims, contradictions, changed names/numbers/dates, or omission of a
central source fact. Do not flag tone, style, brevity, or harmless paraphrasing.
Return an empty issues list if the script is grounded.

Extracted fact checklist:
{fact_checklist}

Full source:
{state["source_text"]}

Script:
{script_json}
"""

    try:
        review = PodcastGroundingReview.model_validate(
            _structured_model(PodcastGroundingReview).invoke(prompt)
        )

    except Exception as exc:
        raise PodcastWorkflowError(
            f"Could not check podcast grounding. Make sure Ollama is running and {OLLAMA_MODEL} is installed."
        ) from exc

    return review.issues


def revise_grounded_script(state: PodcastWorkflowState) -> PodcastScriptResponse:

    script_json = PodcastScriptResponse.model_validate(state["script"]).model_dump_json(
        indent=2
    )

    issue_list = "\n".join(f"- {issue}" for issue in state["issues"])
    fact_checklist = "\n".join(f"- {fact}" for fact in state["facts"])

    prompt = f"""
Revise the podcast script to fix every grounding issue below.
Keep accurate content and the requested {state["format"]} structure.
Do not introduce new facts. Return the complete corrected script in the source language.

Grounding issues:
{issue_list}

Extracted fact checklist:
{fact_checklist}

Full source:
{state["source_text"]}

Current script:
{script_json}
"""

    try:
        script = PodcastScriptResponse.model_validate(
            _structured_model(PodcastScriptResponse).invoke(prompt)
        )

    except Exception as exc:
        raise PodcastWorkflowError(
            f"Could not revise the podcast script. Make sure Ollama is running and {OLLAMA_MODEL} is installed."
        ) from exc

    if state["format"] == "narration":
        script = script.model_copy(
            update={
                "segments": [
                    segment.model_copy(update={"speaker": "host"})
                    for segment in script.segments
                ]
            }
        )

    return script


def build_podcast_workflow(
    checkpointer: object,
    *,
    extract_facts: ExtractFacts = extract_source_facts,
    draft_script: GenerateScript = draft_grounded_script,
    evaluate_script: EvaluateScript = evaluate_script_grounding,
    revise_script: GenerateScript = revise_grounded_script,
) -> object:

    builder = StateGraph(PodcastWorkflowState)

    def extract_node(state: PodcastWorkflowState) -> PodcastWorkflowState:

        return {"facts": extract_facts(state), "status": "extracting"}

    def draft_node(state: PodcastWorkflowState) -> PodcastWorkflowState:

        return {
            "script": draft_script(state).model_dump(mode="json"),
            "status": "evaluating",
        }

    def evaluate_node(state: PodcastWorkflowState) -> PodcastWorkflowState:

        return {
            "issues": evaluate_script(state),
            "status": "evaluating",
        }

    def route_after_evaluation(state: PodcastWorkflowState) -> str:

        if state["issues"] and state["revision_count"] < MAX_PODCAST_REVISIONS:
            return "revise"

        return "prepare_review"

    def revise_node(state: PodcastWorkflowState) -> PodcastWorkflowState:

        return {
            "script": revise_script(state).model_dump(mode="json"),
            "revision_count": state["revision_count"] + 1,
            "status": "evaluating",
        }

    def prepare_review_node(_state: PodcastWorkflowState) -> PodcastWorkflowState:

        return {"status": "awaiting_review"}

    def human_review_node(state: PodcastWorkflowState) -> PodcastWorkflowState:

        approval = interrupt(
            {
                "script": state["script"],
                "facts": state["facts"],
                "issues": state["issues"],
                "revision_count": state["revision_count"],
            }
        )

        validated_approval = PodcastWorkflowApprovalRequest.model_validate(approval)

        return {
            "script": validated_approval.script.model_dump(mode="json"),
            "language_code": validated_approval.language_code,
            "host_voice": validated_approval.host_voice,
            "guest_voice": validated_approval.guest_voice,
            "audio_format": validated_approval.audio_format,
            "status": "approved",
        }

    builder.add_node("extract_facts", extract_node)
    builder.add_node("draft_script", draft_node)
    builder.add_node("evaluate_script", evaluate_node)
    builder.add_node("revise_script", revise_node)
    builder.add_node("prepare_review", prepare_review_node)
    builder.add_node("human_review", human_review_node)

    builder.add_edge(START, "extract_facts")
    builder.add_edge("extract_facts", "draft_script")
    builder.add_edge("draft_script", "evaluate_script")

    builder.add_conditional_edges(
        "evaluate_script",
        route_after_evaluation,
        {
            "revise": "revise_script",
            "prepare_review": "prepare_review",
        },
    )

    builder.add_edge("revise_script", "evaluate_script")

    builder.add_edge("prepare_review", "human_review")

    builder.add_edge("human_review", END)

    return builder.compile(checkpointer=checkpointer)


_workflow_lock = Lock()

_workflow_connection: sqlite3.Connection | None = None

_workflow_graph: object | None = None


def get_podcast_workflow_graph() -> object:

    global _workflow_connection, _workflow_graph

    if _workflow_graph is not None:
        return _workflow_graph

    with _workflow_lock:
        if _workflow_graph is not None:
            return _workflow_graph

        database_path = os.path.abspath(PODCAST_WORKFLOW_DB_PATH)
        os.makedirs(os.path.dirname(database_path), exist_ok=True)

        _workflow_connection = sqlite3.connect(database_path, check_same_thread=False)

        checkpointer = SqliteSaver(_workflow_connection)
        checkpointer.setup()

        _workflow_graph = build_podcast_workflow(checkpointer)

        return _workflow_graph


def _state_to_response(
    workflow_id: str,
    state: PodcastWorkflowState,
) -> PodcastWorkflowResponse:

    if not state or "script" not in state:
        raise PodcastWorkflowNotFoundError("Podcast workflow not found")

    return PodcastWorkflowResponse(
        workflow_id=workflow_id,
        status=state.get("status", "awaiting_review"),
        script=PodcastScriptResponse.model_validate(state["script"]),
        facts=state.get("facts", []),
        issues=state.get("issues", []),
        revision_count=state.get("revision_count", 0),
        audio_job_id=state.get("audio_job_id"),
    )


def start_podcast_workflow(
    request: PodcastScriptRequest,
) -> PodcastWorkflowResponse:

    workflow_id = uuid4().hex

    config = {"configurable": {"thread_id": workflow_id}}

    initial_state: PodcastWorkflowState = {
        "source_text": request.text,
        "format": request.format,
        "duration": request.duration,
        "facts": [],
        "issues": [],
        "revision_count": 0,
        "status": "extracting",
    }

    try:
        get_podcast_workflow_graph().invoke(initial_state, config=config)

        state = get_podcast_workflow_graph().get_state(config).values

        return _state_to_response(workflow_id, state)

    except PodcastWorkflowError:
        raise

    except Exception as exc:
        raise PodcastWorkflowError("Could not run the podcast workflow") from exc


def get_podcast_workflow(workflow_id: str) -> PodcastWorkflowResponse:

    config = {"configurable": {"thread_id": workflow_id}}

    try:
        state = get_podcast_workflow_graph().get_state(config).values
        return _state_to_response(workflow_id, state)

    except PodcastWorkflowNotFoundError:
        raise

    except Exception as exc:
        raise PodcastWorkflowError("Could not load the podcast workflow") from exc


def approve_podcast_workflow(
    workflow_id: str,
    approval: PodcastWorkflowApprovalRequest,
) -> PodcastWorkflowResponse:

    config = {"configurable": {"thread_id": workflow_id}}

    current = get_podcast_workflow(workflow_id)

    if current.status in {"approved", "queued"}:
        return current

    try:
        get_podcast_workflow_graph().invoke(
            Command(resume=approval.model_dump(mode="json")),
            config=config,
        )

        state = get_podcast_workflow_graph().get_state(config).values
        return _state_to_response(workflow_id, state)

    except PodcastWorkflowError:
        raise

    except Exception as exc:
        raise PodcastWorkflowError("Could not approve the podcast workflow") from exc


def get_podcast_workflow_approval(
    workflow_id: str,
) -> PodcastWorkflowApprovalRequest:

    config = {"configurable": {"thread_id": workflow_id}}

    state = get_podcast_workflow_graph().get_state(config).values

    if (
        not state
        or state.get("status") not in {"approved", "queued"}
        or "script" not in state
        or "language_code" not in state
        or "host_voice" not in state
        or "guest_voice" not in state
    ):
        raise PodcastWorkflowError("Podcast workflow is not approved")

    return PodcastWorkflowApprovalRequest(
        script=PodcastScriptResponse.model_validate(state["script"]),
        language_code=state["language_code"],
        host_voice=state["host_voice"],
        guest_voice=state["guest_voice"],
        audio_format=state.get("audio_format", "wav"),
    )


def link_podcast_audio_job(
    workflow_id: str,
    audio_job_id: str,
) -> PodcastWorkflowResponse:

    config = {"configurable": {"thread_id": workflow_id}}

    get_podcast_workflow(workflow_id)

    get_podcast_workflow_graph().update_state(
        config,
        {"audio_job_id": audio_job_id, "status": "queued"},
    )

    return get_podcast_workflow(workflow_id)


def close_podcast_workflow_store() -> None:

    global _workflow_connection, _workflow_graph

    with _workflow_lock:
        if _workflow_connection is not None:
            _workflow_connection.close()

        _workflow_connection = None
        _workflow_graph = None


atexit.register(close_podcast_workflow_store)
