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

- [ ] **Download a completed file twice → both work**
  - Verifies file is not deleted after first download

## v2.0.0 验证

- [ ] 打开两个浏览器（或两台机器）的隐身窗口分别访问，提交两个不同任务 → 各自看到自己的，互不可见
- [ ] 同一浏览器再次刷新主页 → "我的任务"列表保留
- [ ] 提交后立刻看到"排队中 #1"，跑完看到"已完成"+ 下载链接
- [ ] 排队任务点"取消" → 状态变"已取消"
- [ ] 已开始处理的任务点取消 → 不出现取消按钮（应为"查看详情"或下载）
- [ ] 提交 10 个任务后第 11 个 → "队列已满"
- [ ] docker restart 之后：已完成任务仍在列表；正在跑的任务变"失败"
- [ ] 8 天前的任务（可手动改 SQLite 测试）→ 1 小时内被清理
