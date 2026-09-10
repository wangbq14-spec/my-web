from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TaskStatus = Literal[
    "queued", "running", "waiting_approval", "succeeded", "failed", "cancelled"
]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int
    title: str | None = Field(default=None, min_length=1, max_length=200)


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = None


class StepRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_name: str
    status: str
    attempt: int
    structured_input: str | None
    structured_output: str | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_run_id: int
    artifact_type: str
    title: str
    content: str
    metadata: str | None = Field(validation_alias="metadata_json")
    created_at: datetime


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requested_by_step: str
    status: str
    comment: str | None
    decided_at: datetime | None


class TaskRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    workflow_type: str
    title: str
    status: str
    current_step: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[StepRunOut]
    approvals: list[ApprovalOut]
    artifacts: list[ArtifactOut]
