#!/bin/bash
# 查看 vidistill 用户反馈（服务器端）
#
# 用法:
#   ./show_feedback.sh           # 列出所有反馈
#   ./show_feedback.sh 1d        # 只看最近 1 天
#   ./show_feedback.sh count     # 只数总数
#
# 通过容器内的 Python 查询（容器自带 Python，无需在宿主机装 sqlite3）

set -e

CONTAINER=vidistill
DB=/tmp/vidistill/vidistill.db

ARG="${1:-all}"

case "$ARG" in
  count)
    docker exec "$CONTAINER" python -c "
import sqlite3
c = sqlite3.connect('$DB')
n = c.execute('SELECT COUNT(*) FROM feedback').fetchone()[0]
print(f'Total feedback: {n}')
"
    ;;

  1d|day|today)
    docker exec "$CONTAINER" python -c "
import sqlite3
c = sqlite3.connect('$DB')
c.row_factory = sqlite3.Row
rows = c.execute(\"SELECT created_at, contact, content FROM feedback WHERE created_at >= datetime('now', '-1 day') ORDER BY created_at DESC\").fetchall()
print(f'Found {len(rows)} feedback entries in the last day:\n')
for r in rows:
    print(f\"{r['created_at']}  contact={r['contact']}\")
    print(f'  {r[\"content\"]}')
    print()
"
    ;;

  all|*)
    docker exec "$CONTAINER" python -c "
import sqlite3
c = sqlite3.connect('$DB')
c.row_factory = sqlite3.Row
rows = c.execute('SELECT created_at, contact, content FROM feedback ORDER BY created_at DESC').fetchall()
print(f'Total: {len(rows)} feedback entries\n')
for r in rows:
    print(f\"{r['created_at']}  contact={r['contact']}\")
    print(f'  {r[\"content\"]}')
    print()
"
    ;;
esac
