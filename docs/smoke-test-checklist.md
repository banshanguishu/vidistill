# vidistill Smoke Test Checklist

Run before any release. Requires real `DASHSCOPE_API_KEY` and ffmpeg.

## Setup

```bash
poetry install
cp .env.example .env  # fill in DASHSCOPE_API_KEY
poetry run uvicorn vidistill.main:app --port 8000
```

Open http://localhost:8000

## Tests

- [ ] **5-minute YouTube with auto-captions → Markdown**
  - URL: (paste one)
  - Style: 章节笔记
  - Format: Markdown
  - Expect: download .md file with chapters, timestamps

- [ ] **5-minute Bilibili without subtitle → PDF (validates Chinese font + ASR)**
  - URL: (paste one)
  - Style: 章节笔记
  - Format: PDF
  - Expect: PDF opens correctly, Chinese characters render properly (not boxes)

- [ ] **Same video, switch to 短摘要 → Markdown**
  - Expect: shorter file with `## 摘要` and `## 要点`

- [ ] **35-minute video → rejected immediately**
  - Expect: 422 with "超过 30 分钟" message before processing starts

- [ ] **Invalid URL (404 video) → readable error**
  - Expect: 422 with yt-dlp's error surfaced cleanly

- [ ] **Close tab mid-progress → reopen page is blank**
  - Verifies Q11 behavior (no resume)

- [ ] **Submit while another task is running → 409**
  - Expect: "另一个任务正在处理中" message

- [ ] **Download a completed file twice → both work**
  - Verifies file is not deleted after first download
