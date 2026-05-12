# vidistill

Video URL -> AI summary -> Markdown / HTML / PDF.

## Local Development

1. `winget install ffmpeg` (one-time, Windows)
2. `poetry install`
3. `cp .env.example .env` and fill in `DASHSCOPE_API_KEY`
4. `poetry run uvicorn vidistill.main:app --reload --port 8000`
5. Open `http://localhost:8000`

## Testing

```bash
poetry run pytest
```
