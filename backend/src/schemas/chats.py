from datetime import datetime

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    repo_id: str


class CreateSessionResponse(BaseModel):
    session_id: str
    repo_id: str
    created_at: datetime


class SendMessageRequest(BaseModel):
    question: str


class CitationSchema(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    snippet: str
    chunk_type: str
    name: str


class SendMessageResponse(BaseModel):
    message_id: str
    answer: str
    citations: list[CitationSchema]


class MessageSchema(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class SessionSchema(BaseModel):
    id: str
    repo_id: str
    title: str | None
    created_at: datetime
