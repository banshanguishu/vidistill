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

### 推荐：用 `show_feedback.sh` 脚本

把 `show_feedback.sh` 放到服务器 `vidistill/` 目录下（和 `deploy.sh` 同级），
通过容器内的 Python 查（**不依赖宿主机或容器装 sqlite3 CLI**）：

```bash
chmod +x show_feedback.sh        # 首次需要

./show_feedback.sh               # 列出所有反馈
./show_feedback.sh 1d            # 只看最近 1 天
./show_feedback.sh count         # 只数总数
```

### 备选：宿主机 sqlite3（如果你装了）

SQLite 文件通过 docker volume 挂在宿主机 `./data/` 下，宿主机有 `sqlite3` 的话：

```bash
sqlite3 -header -column ./data/vidistill.db \
  "SELECT created_at, contact, content FROM feedback ORDER BY created_at DESC;"
```

宿主机没装就：`sudo apt install -y sqlite3`。

### 备选：docker exec + 容器内 sqlite3

新版本镜像（Dockerfile 已加 sqlite3 包）build 之后可用：

```bash
docker exec vidistill sqlite3 -header -column /tmp/vidistill/vidistill.db \
  "SELECT created_at, contact, content FROM feedback ORDER BY created_at DESC;"
```

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
