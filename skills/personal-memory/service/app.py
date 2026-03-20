"""FastAPI application for the personal memory service."""

from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException

from service.analyzer import list_analysis_results
from service.context_snapshots import search_context_snapshots, sync_session_context
from service.db import get_settings
from service.capture_cycle import consolidate_working_memories, run_capture_cycle
from service.extraction import extract_candidates, extract_review_candidates, should_auto_persist
from service.memory_ops import (
    approve_review_candidate,
    archive_memory,
    delete_memory,
    get_memory,
    list_review_candidates,
    promote_memory,
    reject_review_candidate,
    save_review_candidate,
    search_memories,
    upsert_memory,
)
from service.schemas import (
    ApiResponse,
    ArchiveRequest,
    AnalysisListRequest,
    CaptureRequest,
    CaptureCycleRequest,
    ConsolidateRequest,
    ContextSearchRequest,
    ContextSyncRequest,
    DeleteRequest,
    PromoteRequest,
    ReviewActionRequest,
    ReviewListRequest,
    SearchRequest,
    UpsertRequest,
)

app = FastAPI(title="Personal Memory Service", version="0.1.0")


@app.get("/health", response_model=ApiResponse)
def health() -> ApiResponse:
    settings = get_settings()
    return ApiResponse(
        ok=True,
        data={
            "service": "personal-memory",
            "user_code": settings["memory_user"],
            "host": settings["service_host"],
            "port": settings["service_port"],
        },
    )


@app.get("/memory/{memory_id}", response_model=ApiResponse)
def get_memory_item(memory_id: int, user_code: Optional[str] = None) -> ApiResponse:
    row = get_memory(memory_id, user_code)
    if not row:
        raise HTTPException(status_code=404, detail="memory not found")
    return ApiResponse(ok=True, data=row)


@app.post("/memory/search", response_model=ApiResponse)
def search_memory_items(request: SearchRequest) -> ApiResponse:
    rows = search_memories(
        query=request.query,
        user_code=request.user_code,
        memory_type=request.memory_type,
        tags=request.tags,
        include_archived=request.include_archived,
        limit=request.limit,
    )
    return ApiResponse(ok=True, data={"items": rows, "count": len(rows)})


@app.post("/context/sync", response_model=ApiResponse)
def sync_context(request: ContextSyncRequest) -> ApiResponse:
    payload = sync_session_context(
        session_key=request.session_key,
        turns=[turn.model_dump() for turn in request.turns],
        user_code=request.user_code,
        topic_hint=request.topic_hint,
        source_ref=request.source_ref,
        extract_memory=request.extract_memory,
    )
    return ApiResponse(ok=True, data=payload)


@app.post("/context/search", response_model=ApiResponse)
def search_context(request: ContextSearchRequest) -> ApiResponse:
    rows = search_context_snapshots(
        query=request.query,
        user_code=request.user_code,
        session_key=request.session_key,
        snapshot_level=request.snapshot_level,
        limit=request.limit,
    )
    return ApiResponse(ok=True, data={"items": rows, "count": len(rows)})


@app.post("/memory/upsert", response_model=ApiResponse)
def upsert_memory_item(request: UpsertRequest) -> ApiResponse:
    row = upsert_memory(request.model_dump())
    return ApiResponse(ok=True, data=row)


@app.post("/memory/promote", response_model=ApiResponse)
def promote_memory_item(request: PromoteRequest) -> ApiResponse:
    row = promote_memory(request.model_dump())
    return ApiResponse(ok=True, data=row)


@app.post("/memory/capture", response_model=ApiResponse)
def capture_memory_candidates(request: CaptureRequest) -> ApiResponse:
    candidates = extract_candidates(request.text)
    review_candidates = extract_review_candidates(request.text)
    persisted = []
    remaining = []
    review_items = []
    for candidate in candidates:
        auto_persist = request.auto_persist or should_auto_persist(candidate)
        if auto_persist:
            payload = candidate.copy()
            payload["user_code"] = request.user_code
            persisted.append(upsert_memory(payload))
        else:
            remaining.append(candidate)
    for candidate in review_candidates:
        user_code = request.user_code or str(get_settings()["memory_user"])
        review_items.append(
            save_review_candidate(user_code=user_code, source_text=request.text, candidate=candidate)
        )
    return ApiResponse(
        ok=True,
        data={
            "persisted": persisted,
            "persisted_count": len(persisted),
            "candidates": remaining,
            "candidate_count": len(remaining),
            "review_candidates": review_items,
            "review_candidate_count": len(review_items),
        },
    )


@app.post("/memory/capture-cycle", response_model=ApiResponse)
def capture_memory_cycle(request: CaptureCycleRequest) -> ApiResponse:
    payload = run_capture_cycle(
        user_text=request.user_text,
        assistant_text=request.assistant_text,
        user_code=request.user_code,
        session_key=request.session_key,
        source_ref=request.source_ref,
        consolidate=request.consolidate,
    )
    return ApiResponse(ok=True, data=payload)


@app.post("/memory/capture-cycle-async", response_model=ApiResponse)
def capture_memory_cycle_async(
    request: CaptureCycleRequest, background_tasks: BackgroundTasks
) -> ApiResponse:
    background_tasks.add_task(
        run_capture_cycle,
        user_text=request.user_text,
        assistant_text=request.assistant_text,
        user_code=request.user_code,
        session_key=request.session_key,
        source_ref=request.source_ref,
        consolidate=request.consolidate,
    )
    return ApiResponse(
        ok=True,
        data={
            "accepted": True,
            "session_key": request.session_key,
            "user_code": request.user_code or str(get_settings()["memory_user"]),
        },
    )


@app.post("/memory/consolidate", response_model=ApiResponse)
def consolidate_memory_items(request: ConsolidateRequest) -> ApiResponse:
    payload = consolidate_working_memories(
        user_code=request.user_code,
        session_key=request.session_key,
    )
    return ApiResponse(ok=True, data=payload)


@app.post("/memory/analysis/list", response_model=ApiResponse)
def list_memory_analysis(request: AnalysisListRequest) -> ApiResponse:
    rows = list_analysis_results(
        user_code=request.user_code,
        session_key=request.session_key,
        limit=request.limit,
    )
    return ApiResponse(ok=True, data={"items": rows, "count": len(rows)})


@app.post("/memory/review/list", response_model=ApiResponse)
def review_candidate_list(request: ReviewListRequest) -> ApiResponse:
    rows = list_review_candidates(request.user_code, request.limit)
    return ApiResponse(ok=True, data={"items": rows, "count": len(rows)})


@app.post("/memory/review/action", response_model=ApiResponse)
def review_candidate_action(request: ReviewActionRequest) -> ApiResponse:
    if request.action == "approve":
        payload = approve_review_candidate(request.id, request.user_code)
    elif request.action == "reject":
        payload = reject_review_candidate(request.id, request.user_code)
    else:
        raise HTTPException(status_code=400, detail="unsupported review action")

    if not payload:
        raise HTTPException(status_code=404, detail="review candidate not found or already processed")
    return ApiResponse(ok=True, data=payload)


@app.post("/memory/archive", response_model=ApiResponse)
def archive_memory_item(request: ArchiveRequest) -> ApiResponse:
    row = archive_memory(request.id, request.user_code)
    if not row:
        raise HTTPException(status_code=404, detail="memory not found")
    return ApiResponse(ok=True, data=row)


@app.post("/memory/delete", response_model=ApiResponse)
def delete_memory_item(request: DeleteRequest) -> ApiResponse:
    row = delete_memory(request.id, request.user_code)
    if not row:
        raise HTTPException(status_code=404, detail="memory not found")
    return ApiResponse(ok=True, data=row)
