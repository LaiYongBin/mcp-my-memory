"""Shared request/response models."""

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(default="")
    user_code: Optional[str] = None
    memory_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    include_archived: bool = False
    limit: int = Field(default=10, ge=1, le=100)


class UpsertRequest(BaseModel):
    id: Optional[int] = None
    user_code: Optional[str] = None
    memory_type: str = "fact"
    title: str
    content: str
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source_type: str = "manual"
    source_ref: Optional[str] = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    importance: int = Field(default=5, ge=1, le=10)
    status: str = "active"
    is_explicit: bool = False
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class DeleteRequest(BaseModel):
    id: int
    user_code: Optional[str] = None


class ArchiveRequest(BaseModel):
    id: int
    user_code: Optional[str] = None


class PromoteRequest(BaseModel):
    text: str
    title: Optional[str] = None
    user_code: Optional[str] = None
    memory_type: str = "fact"
    tags: List[str] = Field(default_factory=list)
    source_type: str = "conversation"
    source_ref: Optional[str] = None
    explicit: bool = False


class CaptureRequest(BaseModel):
    text: str
    user_code: Optional[str] = None
    auto_persist: bool = False


class ReviewListRequest(BaseModel):
    user_code: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


class ReviewActionRequest(BaseModel):
    id: int
    user_code: Optional[str] = None
    action: str


class ApiResponse(BaseModel):
    ok: bool
    data: Optional[Any] = None
    message: str = ""
