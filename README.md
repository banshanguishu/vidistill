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

## 查看用户反馈（服务器）

SQLite 文件通过 docker volume 挂在宿主机 `./data/` 下，**在宿主机直接查最方便**
（不用进容器，免去镜像装 sqlite3 的麻烦）：

```bash
# 在 docker-compose.yml 所在目录执行
sqlite3 -header -column ./data/vidistill.db \
  "SELECT created_at, contact, content FROM feedback ORDER BY created_at DESC;"
```

只看最近一天：

```bash
sqlite3 -header -column ./data/vidistill.db \
  "SELECT * FROM feedback WHERE created_at >= datetime('now', '-1 day');"
```

数一下总数：

```bash
sqlite3 ./data/vidistill.db "SELECT COUNT(*) FROM feedback;"
```

如果宿主机没装 `sqlite3` CLI：`sudo apt install -y sqlite3`。

如果你嫌不方便在宿主机装，也可以用容器里的 Python（Python 自带 sqlite3 模块）：

```bash
docker exec vidistill python -c "
import sqlite3
c = sqlite3.connect('/tmp/vidistill/vidistill.db')
c.row_factory = sqlite3.Row
for r in c.execute('SELECT created_at, contact, content FROM feedback ORDER BY created_at DESC'):
    print(f\"{r['created_at']}  contact={r['contact']}\")
    print(f'  {r[\"content\"]}')
    print()
"
```

**注意**：Dockerfile 已加 `sqlite3` 作为系统依赖（用于 `docker exec vidistill sqlite3 ...`），但旧版本镜像里没有。要 `docker exec` 用 sqlite3，先 rebuild 一次镜像。

本地开发环境查反馈用 `poetry run python scripts/show_feedback.py`。

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
