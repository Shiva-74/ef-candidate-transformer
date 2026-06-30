from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class RawFieldValue(BaseModel):
    field:      str
    value:      Any
    source:     str
    method:     str
    confidence: float


class Skill(BaseModel):
    name:       str
    confidence: float = 0.6
    sources:    List[str] = Field(default_factory=list)


class Experience(BaseModel):
    company:  Optional[str] = None
    title:    Optional[str] = None
    start:    Optional[str] = None
    end:      Optional[str] = None
    summary:  Optional[str] = None


class Education(BaseModel):
    institution: Optional[str] = None
    degree:      Optional[str] = None
    field:       Optional[str] = None
    start_year:  Optional[str] = None
    end_year:    Optional[str] = None


class ProvenanceEntry(BaseModel):
    field:      str
    source:     str
    method:     str
    confidence: float


class Location(BaseModel):
    city:    Optional[str] = None
    region:  Optional[str] = None
    country: Optional[str] = None


class Links(BaseModel):
    linkedin:  Optional[str] = None
    github:    Optional[str] = None
    portfolio: Optional[str] = None
    other:     List[str] = Field(default_factory=list)


class Candidate(BaseModel):
    candidate_id:       str = ""
    full_name:          Optional[str] = None
    emails:             List[str] = Field(default_factory=list)
    phones:             List[str] = Field(default_factory=list)
    location:           Location  = Field(default_factory=Location)
    links:              Links     = Field(default_factory=Links)
    headline:           Optional[str] = None
    years_experience:   Optional[float] = None
    skills:             List[Skill]      = Field(default_factory=list)
    experience:         List[Experience] = Field(default_factory=list)
    education:          List[Education]  = Field(default_factory=list)
    projects:           List[str]        = Field(default_factory=list)
    certifications:     List[str]        = Field(default_factory=list)
    achievements:       List[str]        = Field(default_factory=list)
    provenance:         List[ProvenanceEntry] = Field(default_factory=list)
    overall_confidence: float = 0.0