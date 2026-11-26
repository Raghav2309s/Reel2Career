# Reel2Career

Reel2Career is an in-development personal project for turning
career-related Instagram Reel content into structured, evidence-backed
career information.

The current repository focuses on media processing, evidence storage,
and experimental AI-analysis workflows. It is not presented as a
finished or production-ready application.

## Current implementation

The repository contains code for:

- Audio and video-frame extraction.
- Audio transcription.
- OCR processing of video frames and carousel images.
- Ingestion of transcript and OCR evidence into a database.
- Per-reel processing status and error reporting.
- Integration points for batch AI analysis and career synthesis.
- GitHub resource discovery, verification, and persistence modules.

Code presence does not mean every component has been validated
end to end. See Verification Status and Known Limitations.

## Technology

- Python
- SQLite
- SQLAlchemy-based database integration
- External transcription, OCR, and AI dependencies

A reproducible dependency specification and tested environment
details are being documented.

## Project structure

```text
backend/app/        Processing, persistence, analysis, and test modules
vault/              Project artifacts; review contents before sharing
audio.py            Audio extraction utilities
extract_frames.py   Frame extraction utilities
sync.py             Synchronization-related code
```

## Setup

Setup is currently developer-oriented.

1. Clone the repository.
2. Create and activate a Python virtual environment.
3. Install dependencies from the project's verified dependency file
   once documented.
4. Configure the services required by the components being run.
5. Provide permitted local media and synchronization inputs.

Exact supported Python version, dependency versions, environment
variables, and external-tool requirements must be verified before
these instructions can be described as reproducible.

Do not commit API keys, login sessions, cookies, private media,
or personal database contents.

## Pipeline usage

The pipeline script exposes these command-line options:

```bash
python backend/app/process_pipeline.py --help
```

Attempt media/evidence processing without the AI-analysis stage:

```bash
python backend/app/process_pipeline.py --no-ai
```

This is an invocation example, not a guarantee of a successful run.
It still requires dependencies, input state, and local media.

The --no-ai option does not guarantee that every processing stage
is offline, free, or independent of external services.

## Tests

Test modules are located under backend/app.

Before running the full suite:

- Review test imports and fixtures.
- Identify tests requiring API credentials or network access.
- Ensure tests use disposable data rather than personal databases.
- Determine whether pytest, unittest, or direct script execution
  is appropriate for each test group.

No passing test count is claimed in this README until a reproducible
test run has been recorded.

## Known limitations

- End-to-end operation has not been verified in the documentation.
- The pipeline references ai_extract, while the reviewed directory
  listing contained ai_extracted.py. Import resolution needs checking.
- Some functionality depends on locally available media and state.
- AI-output quality has not been established through a documented
  evaluation.
- Semantic search, skill-gap analysis, personalized roadmaps, and
  other planned features must not be treated as completed without
  implementation and validation evidence.

## Verification status

| Area | Status |
|---|---|
| Selected source files | Reviewed |
| Reproducible setup | Not yet documented |
| Automated test results | Not yet recorded |
| Full end-to-end pipeline | Not yet verified |
| Public deployment | Not confirmed |

## Roadmap

- Document and validate a clean installation.
- Resolve pipeline integration issues.
- Separate offline tests from external-service tests.
- Record reproducible test results.
- Evaluate extraction quality on representative examples.
- Extend career-information features after the pipeline is validated.

## Contributions

Personal project by Raghav Singhal.

Specific implementation ownership should be described accurately
where external contributions or reused code are involved.
