from pydantic import BaseModel, Field, field_validator


class JobDescription(BaseModel):
    role: str
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    minimum_experience: float | None = None
    education_requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    company: str | None = None
    role: str | None = None
    duration: str | None = None
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)


class Resume(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    total_experience_years: float | None = None
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    candidate_name: str | None = None
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    experience_requirement_met: bool | None = None
    score: float
    verdict: str = ""

    @field_validator("experience_requirement_met", mode="before")
    @classmethod
    def coerce_experience_flag(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if normalized in {"yes", "true", "met", "y"}:
            return True
        if normalized in {"no", "false", "not met", "unmet", "n"}:
            return False
        if normalized in {"", "unknown", "n/a", "null", "none"}:
            return None
        return value

    @field_validator("score", mode="before")
    @classmethod
    def coerce_score(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().rstrip("%")
        return value

    @field_validator("score")
    @classmethod
    def clamp_score(cls, value: float) -> float:
        return max(0.0, min(100.0, value))
