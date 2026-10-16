# Resume Evaluator

A command-line tool that reads resumes from a folder, compares each one with a job description, and prints the strongest matches. Groq extracts structure from the job and from each resume, then scores the fit.

The bundled job is a Senior Full-Stack Engineer (Tech Lead) role in Vadodara.

## Features

- Loads `GROQ_API_KEY` from the environment or a `.env` file.
- Turns the job description into a role, required and preferred skills, minimum experience, education, and responsibilities.
- Reads `.pdf` and `.docx` files from `resumes/`, including text stored in Word tables.
- Parses each resume into contact details, total experience, skills, work history (internships included), education, projects, and certifications.
- Scores every parsed resume from 0 to 100 and records matching skills, missing skills, whether the experience requirement is met, and a short verdict.
- Skips a file that cannot be read or parsed and continues with the rest.
- Sorts candidates by score and prints the top 3.
- Waits 5 seconds between Groq calls to stay under rate limits.

## Setup

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
```

Put your Groq API key in `.env`:

```bash
GROQ_API_KEY=your_key_here
```

Drop candidate files into `resumes/`. Only `.pdf` and `.docx` are read. Personal files in that folder stay local and are gitignored.

Three fake candidates are already included for a trial run:

- `resumes/dummy_strong_match.docx` — Aarav Mehta, close fit for the bundled role
- `resumes/dummy_partial_match.docx` — Neha Kapoor, mostly frontend
- `resumes/dummy_weak_match.docx` — Rahul Desai, Java backend with no React or Node.js

Names, phone numbers, and emails in those files are made up.

## Usage

```bash
uv run resume-evaluator
```

On this local checkout, `uv run day5-resume-evaluator` runs the same command.

Example output:

```text
Extracting job requirements...
Role: Senior Full-Stack Engineer

Processing: candidate.pdf
Score: 82.0

Top candidates
1. Ada Lovelace — 82.0% (candidate.pdf)
   Matching skills: TypeScript, React, Node.js, PostgreSQL
   Missing skills: NestJS, Redis
   Experience requirement met: yes
   Verdict: Strong full-stack match with a gap in NestJS.
```

To score people against a different role, replace the text in `src/job_description.txt`.

## How a run works

1. The job text is sent to `openai/gpt-oss-120b` on Groq and validated as a `JobDescription`.
2. Each resume is converted to plain text, then validated as a `Resume`.
3. The structured job and resume are compared and validated as a `MatchResult`.
4. Scores are sorted from highest to lowest. The first three are printed.

The model is instructed not to invent skills or experience. Scores are still model judgments, so two runs can differ.

## Project layout

```text
main.py                 # launcher
src/
  evaluator.py          # Groq calls, ranking, CLI
  models.py             # job, resume, and match schemas
  readers.py            # PDF and DOCX text extraction
  job_description.txt   # role used for scoring
resumes/                # local candidate files
```

## Feature audit

Reviewed against the original single-file script.

| Area | Finding |
| --- | --- |
| Job extraction | Works. The role text was embedded in `main.py`; it now lives in `job_description.txt`. |
| Resume reading | Works for text-based PDF and DOCX. Word tables were read, but merged cells were repeated. Duplicate cells in a row are now dropped. |
| Resume parsing | Works, with typos in the schema (`skills_userd`, `project`) and prompts that asked the model for the wrong shape. Field names and instructions now match. |
| Scoring | The prompt asked for a name, skill gaps, experience fit, a percentage, and a verdict, while the schema only had `score` and an untyped `details` object. Scoring now uses those six fields, and the score is kept between 0 and 100. |
| Ranking | Works. Still prints the top 3 only and does not save a file. |
| CLI | `pyproject.toml` pointed at a stub that printed `Hello from day5-resume-evaluator!`. The installed command now runs the evaluator. Importing the package no longer calls the API. |
| Failures | A missing API key, missing folder, empty folder, bad JSON, or one unreadable file used to abort the whole run. Expected failures now exit or skip with a message. |
| Secrets | `.env` was not ignored. It is ignored now. Resumes are ignored too. |

Still out of scope:

- Scanned or image-only PDFs are not OCR'd, so they extract as empty and are skipped.
- `.doc`, `.txt`, and other formats are ignored.
- There is one job description per run, not a job board or upload UI.
- Results are printed, not written to JSON or CSV.
- The 5-second pause is fixed.
- There is no automated test suite. Text extraction was checked locally against the sample PDF and a generated DOCX; live Groq scoring was not re-run during cleanup.
