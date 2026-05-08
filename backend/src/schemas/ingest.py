from pydantic import BaseModel


class IngestRepositoryRequest(BaseModel):
    github_url: str


class IngestRepositoryResponse(BaseModel):
    repo_id: str
    status: str
    message: str


class RepositoryStatusResponse(BaseModel):
    repo_id: str
    github_url: str
    owner: str | None
    name: str | None
    status: str
    total_files: int
    processed_files: int
