from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


class Entities(BaseModel):
    line_num: str | None = None
    station_name: str | None = None
    specialty: str | None = None
    device: str | None = None
    fault_phenomenon: str | None = None
    time_range: TimeRange | None = None
    compare_dimension: Literal["line", "station", "specialty"] | None = None


class StatisticsRequest(BaseModel):
    entities: Entities
    query_type: Literal["ranking", "count", "comparison"] = "count"


class ResponsibilityRequest(BaseModel):
    entities: Entities


class DiagnosisSupportRequest(BaseModel):
    user_query: str = Field(min_length=1)
    entities: Entities
    vector_candidate_ids: list[str] = Field(default_factory=list)
    limit: int = 100


class DiagnosisSupportLayerRequest(BaseModel):
    layer_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    evidence_level: str = Field(min_length=1)
    priority: int = 1
    entities: Entities
    vector_candidate_ids: list[str] = Field(default_factory=list)
    limit: int = 100


class DiagnosisSupportBatchRequest(BaseModel):
    user_query: str = Field(min_length=1)
    layers: list[DiagnosisSupportLayerRequest] = Field(default_factory=list)
