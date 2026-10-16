import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import TypeVar

from dotenv import load_dotenv
from groq import APIError, Groq
from pydantic import BaseModel, ValidationError

from src.models import JobDescription, MatchResult, Resume
from src.readers import SUPPORTED_SUFFIXES, read_resume

MODEL = "openai/gpt-oss-120b"
REQUEST_PAUSE_SECONDS = 5
DEFAULT_RESUME_DIR = Path("resumes")
JOB_DESCRIPTION_PATH = Path(__file__).with_name("job_description.txt")
TOP_N = 3
ModelT = TypeVar("ModelT", bound=BaseModel)


class EvaluationError(RuntimeError):
    """A resume or job call could not be turned into structured data."""


@dataclass
class CandidateResult:
    file_name: str
    match: MatchResult


class GroqJSONClient:
    def __init__(self, client: Groq, model: str = MODEL) -> None:
        self._client = client
        self._model = model
        self._calls = 0

    def complete(self, messages: list[dict[str, str]]) -> dict:
        if self._calls:
            time.sleep(REQUEST_PAUSE_SECONDS)
        self._calls += 1
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except APIError as exc:
            raise EvaluationError(f"Groq request failed: {exc}") from exc

        content = response.choices[0].message.content
        if not content:
            raise EvaluationError("The model returned an empty response.")
        return _parse_json_object(content)


def load_job_description(path: Path = JOB_DESCRIPTION_PATH) -> str:
    return path.read_text(encoding="utf-8")


def extract_job(client: GroqJSONClient, job_text: str) -> JobDescription:
    schema = JobDescription.model_json_schema()
    messages = [
        {
            "role": "system",
            "content": dedent(f"""
                You are an expert HR assistant.
                Extract structured information from the job description.
                Return ONLY valid JSON matching this schema: {schema}

                Do NOT return the schema itself.
                Do NOT return fields like "properties", "title", or "type".
                If minimum experience is not mentioned, return null.
                If a list has no information, return an empty list.
                Do not invent information.
            """).strip(),
        },
        {
            "role": "user",
            "content": f"Analyze the following job description:\n{job_text}",
        },
    ]
    return _validate(JobDescription, client.complete(messages), "job description")


def parse_resume(client: GroqJSONClient, resume_text: str) -> Resume:
    schema = Resume.model_json_schema()
    messages = [
        {
            "role": "system",
            "content": dedent(f"""
                You are an expert resume parser.
                Extract information from the resume based on meaning, not only exact section headings.

                Different resumes use different headings. Experience, Professional Experience,
                Work History, Employment, and Internships can all contain relevant experience.
                Skills may appear in a skills section, work experience, internships, or projects.

                Return ONLY valid JSON matching this schema: {schema}

                Rules:
                1. Do not invent information.
                2. If a value is missing, return null.
                3. If a list has no information, return an empty list.
                4. Include internships inside experience.
                5. Extract skills mentioned anywhere in the resume.
            """).strip(),
        },
        {
            "role": "user",
            "content": f"Parse the following resume:\n{resume_text}",
        },
    ]
    return _validate(Resume, client.complete(messages), "resume")


def score_candidate(
    client: GroqJSONClient,
    job: JobDescription,
    resume: Resume,
) -> MatchResult:
    schema = MatchResult.model_json_schema()
    messages = [
        {
            "role": "system",
            "content": dedent(f"""
                You are an HR recruiter.
                Compare the candidate with the job and return ONLY valid JSON matching this schema:
                {schema}

                score is a number from 0 to 100.
                experience_requirement_met is true, false, or null when experience cannot be judged.
                Do not invent skills that are not supported by the resume or the job.
            """).strip(),
        },
        {
            "role": "user",
            "content": (
                "JOB DESCRIPTION:\n"
                f"{job.model_dump_json(indent=2)}\n\n"
                "CANDIDATE RESUME:\n"
                f"{resume.model_dump_json(indent=2)}"
            ),
        },
    ]
    return _validate(MatchResult, client.complete(messages), "match result")


def evaluate_resumes(
    client: GroqJSONClient,
    job: JobDescription,
    resume_dir: Path = DEFAULT_RESUME_DIR,
) -> list[CandidateResult]:
    if not resume_dir.is_dir():
        raise EvaluationError(f"Resume folder not found: {resume_dir}")

    files = sorted(
        path
        for path in resume_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not files:
        raise EvaluationError(
            f"No .pdf or .docx files found in {resume_dir}."
        )

    results: list[CandidateResult] = []
    for file_path in files:
        print(f"\nProcessing: {file_path.name}")
        try:
            resume_text = read_resume(file_path) or ""
            if not resume_text.strip():
                raise EvaluationError("No text could be extracted from the file.")
            resume = parse_resume(client, resume_text)
            match = score_candidate(client, job, resume)
        except Exception as exc:
            print(f"Skipped {file_path.name}: {exc}")
            continue

        if match.candidate_name is None:
            match.candidate_name = resume.name
        print(f"Score: {match.score}")
        results.append(CandidateResult(file_name=file_path.name, match=match))

    results.sort(key=lambda candidate: candidate.match.score, reverse=True)
    return results


def print_top_candidates(results: list[CandidateResult], limit: int = TOP_N) -> None:
    print("\nTop candidates")
    if not results:
        print("No candidates were scored.")
        return

    for index, candidate in enumerate(results[:limit], start=1):
        match = candidate.match
        name = match.candidate_name or candidate.file_name
        experience = _format_experience(match.experience_requirement_met)
        print(f"{index}. {name} — {match.score}% ({candidate.file_name})")
        print(f"   Matching skills: {_format_list(match.matching_skills)}")
        print(f"   Missing skills: {_format_list(match.missing_skills)}")
        print(f"   Experience requirement met: {experience}")
        print(f"   Verdict: {match.verdict or 'n/a'}")


def main() -> None:
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY was not found. Add it to a .env file.")

    client = GroqJSONClient(Groq(api_key=api_key))
    print("Extracting job requirements...")
    try:
        job = extract_job(client, load_job_description())
        print(f"Role: {job.role}")
        results = evaluate_resumes(client, job)
    except EvaluationError as exc:
        raise SystemExit(str(exc)) from exc
    print_top_candidates(results)


def _parse_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"Model response was not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise EvaluationError("Model response was not a JSON object.")
    return data


def _validate(model: type[ModelT], data: dict, label: str) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise EvaluationError(f"Could not parse {label}: {exc}") from exc


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _format_experience(met: bool | None) -> str:
    if met is None:
        return "unknown"
    return "yes" if met else "no"
