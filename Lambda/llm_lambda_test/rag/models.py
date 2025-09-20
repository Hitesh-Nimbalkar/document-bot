
from typing import List, Dict, Any
from pydantic import BaseModel, Field
# Minimal models only (input/output) as per request
class FiltersInput(BaseModel):
    project_name: str
    query: str
    context_info: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)
class FiltersOutput(BaseModel):
    must: List[Dict[str, Any]] = Field(default_factory=list)
    should: List[Dict[str, Any]] = Field(default_factory=list)
    not_: List[Dict[str, Any]] = Field(default_factory=list)
class RerankInput(BaseModel):
    query: str
    results: List[Dict[str, Any]]
    top_k: int = 5
    context_info: Dict[str, Any] = Field(default_factory=dict)
class RerankOutput(BaseModel):
    query: str
    top_k: int
    results: List[Dict[str, Any]]
    strategy: str = "llm+metadata"

