# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project shape

Video URL → AI summary → Markdown / HTML / PDF, served as a single-user web tool. Deliberately minimal: no database, no auth, no job history, no concurrent pipelines, no automatic retries. **Treat "let's add X for robustness" with suspicion** — the spec rejects most such additions on purpose.

The authoritative design lives in `docs/superpowers/specs/2026-05-12-vidistill-design.md` and `docs/superpowers/plans/2026-05-12-vidistill.md`. When something in code seems wrong, check the spec first before "fixing" it.

## Common commands

```powershell
poetry install
poetry run uvicorn vidistill.main:app --reload --port 8000   # dev server
poetry run pytest                                            # all tests
poetry run pytest tests/unit/test_jobs.py                    # single file
poetry run pytest tests/unit/test_jobs.py::test_name -v      # single test
docker build -t vidistill . ; docker run -p 8000:8000 --env-file .env vidistill
```

Requires `DASHSCOPE_API_KEY` in `.env` (copy from `.env.example`) and `ffmpeg` on PATH (`winget install ffmpeg` on Windows). Pytest is configured with `pythonpath = ["src"]` and `asyncio_mode = "auto"` in `pyproject.toml`.

Manual smoke tests before release: `docs/smoke-test-checklist.md`.

## Architecture

Request flow is a strict pipeline: `routes.py` (HTTP) → `pipeline.py` (orchestration) → `adapters/*` (external I/O) → `renderers/*` (file output). All three layers are mocked independently in tests — keep the boundaries clean.

- **`main.py`** — `build_app()` factory; the module-level `app` is what uvicorn loads. A single global `_GLOBAL_STORE` is attached to `app.state.store`. Tests use `build_app(output_dir=tmp_path)` to inject a temp output directory.
- **`routes.py`** — three endpoints: `POST /jobs` (creates), `GET /jobs/{id}` (status), `GET /jobs/{id}/download/{fmt}`. Pipeline runs via FastAPI `BackgroundTasks` in the same process — no Celery, no queue.
- **`pipeline.py`** — `process_video()` walks phases: `fetching` → `transcribing` (skipped if subtitle exists) → `summarizing` → `rendering` → `done`. Renders **all three formats per job**; the user picks at download time. `md` and `html` are mandatory; `pdf` is best-effort (WeasyPrint failures on missing GTK runtime are swallowed, `output_paths["pdf"] = None`). Intermediate audio/subtitle files are deleted in `_cleanup_intermediate` regardless of outcome.
- **`jobs.py`** — `JobStore` is in-memory with a `threading.Lock`. State is lost on restart, by design. The single-slot semaphore (`try_acquire_slot`/`release_slot`) enforces "one pipeline at a time" — a second `POST /jobs` while one is running returns 409.
- **`adapters/video.py`** — yt-dlp wrapper. `fetch_metadata` for duration check, `fetch_subtitle` (tries `zh`, `zh-CN`, `en` VTT), `download_audio` does a two-step process: yt-dlp grabs raw audio, then a separate ffmpeg call resamples to **16 kHz mono mp3** (required by `paraformer-realtime-v2`; `_resample_to_16k_mono` is isolated so tests can patch it).
- **`adapters/asr.py`** — DashScope `Recognition` (paraformer-realtime-v2). The **realtime** model accepts a local file path; the batch model would require a public HTTPS URL, which we don't have. Don't switch back.
- **`adapters/llm.py`** — Qwen via OpenAI SDK against DashScope's compatible-mode endpoint, with `response_format={"type": "json_object"}`. Prompts in `prompts.py` enforce the JSON schema for `short` vs `chapters` style.
- **`renderers/`** — `markdown.py` is the source of truth for content shape and filename sanitization (`sanitize_filename` is reused everywhere). `html.py` wraps the markdown render in a Chinese-font-friendly template. `pdf.py` is imported **lazily** inside `pipeline._get_renderer` — never import it at module top level, or the dev server will fail on Windows without GTK libs.

## Constraints worth knowing before editing

- **Audio must be 16 kHz mono mp3** for the ASR adapter. If you touch `video.download_audio`, preserve the explicit ffmpeg resample step.
- **One job at a time** is enforced in `routes.create_job` via `JobStore.try_acquire_slot`. The slot is released in `_runner`'s `finally`. Don't bypass this to "support concurrent jobs" — the spec rules it out.
- **Max video duration 30 min** (`config.max_video_duration_seconds = 1800`). Enforced in `routes.create_job` against yt-dlp metadata, before any download.
- **Output dir** defaults to `/tmp/vidistill` (Linux/container) and is overridden in tests. Each job gets its own `{output_dir}/{job_id}/` subdirectory.
- **PDF is best-effort.** On Windows dev machines without GTK, PDF rendering fails and the download endpoint returns 404 for `fmt=pdf` with a clear message. Don't change PDF to "fail the whole job" without revising the spec.
- **Domain errors** all inherit from `VidistillError` (`exceptions.py`). The pipeline catches these and writes `error` to job state; anything else becomes "未预期错误". Raise the typed exceptions from adapters, don't leak raw library errors.

## Test layout

- `tests/unit/` — adapter and renderer tests with mocks; no network, no ffmpeg required for unit tests (the resample step is patched).
- `tests/integration/` — `test_pipeline.py` and `test_routes.py` use fixture JSON files in `tests/fixtures/` (yt-dlp metadata responses, Paraformer responses, Qwen responses) to exercise the full flow with adapters mocked at their boundary.
- `tests/conftest.py` sets `DASHSCOPE_API_KEY=test-key` via autouse fixture so `load_config()` never trips.
