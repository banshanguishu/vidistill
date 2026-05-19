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

## Troubleshooting

### "正在抓取视频信息..." stuck for minutes / yt-dlp 卡死

容器内的 yt-dlp 进程或网络连接可能卡死。重启容器通常可解：

```bash
docker-compose restart vidistill
```

若复发，按顺序排查：

1. **`docker logs vidistill --tail 200`** —— 看 yt-dlp 最后的输出。卡在哪个 site 的 extractor？是否有 `Unable to download webpage` / `Retrying`？
2. **`docker stats vidistill`** —— 看 CPU / 内存是否异常高（卡在某个内部死循环）
3. **`docker-compose restart vidistill`** —— 应急恢复手段，会清空所有进程和 socket，让 yt-dlp 从干净状态重启
