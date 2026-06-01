import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _default_frontend_dist() -> Path:
    # config.py 位于 <repo>/src/vidistill/config.py → parents[2] 为仓库根
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


@dataclass(frozen=True)
class Config:
    dashscope_api_key: str
    dashscope_compatible_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    paraformer_model: str = "paraformer-realtime-v2"
    output_dir: Path = field(default_factory=lambda: Path("/tmp/vidistill"))
    log_dir: Path = field(default_factory=lambda: Path("/tmp/vidistill"))
    db_path: Optional[Path] = None  # v2 新增；None 表示 output_dir / "vidistill.db"
    frontend_dist_dir: Path = field(default_factory=_default_frontend_dist)
    max_video_duration_seconds: int = 1800
    pipeline_timeout_seconds: int = 1800
    min_free_disk_mb: int = 500

    def effective_db_path(self) -> Path:
        return self.db_path if self.db_path else self.output_dir / "vidistill.db"


def load_config() -> Config:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY environment variable is required. "
            "Copy .env.example to .env and fill it in."
        )
    log_dir_env = os.environ.get("LOG_DIR")
    kwargs: dict = {"dashscope_api_key": api_key}
    if log_dir_env:
        kwargs["log_dir"] = Path(log_dir_env)
    return Config(**kwargs)
