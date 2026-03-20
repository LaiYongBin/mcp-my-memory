"""FastAPI application for the personal memory service."""

from typing import Optional

from fastapi import FastAPI, HTTPException

from service.db import get_settings
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
    CaptureRequest,
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
