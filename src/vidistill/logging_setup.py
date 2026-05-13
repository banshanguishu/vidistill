import logging
from pathlib import Path

_CONFIGURED = False


def setup_logging(log_dir: Path) -> None:
    """Configure the `vidistill` logger with a file + console handler.

    Idempotent — safe to call multiple times (e.g., across TestClient setups).
    Output file path: <log_dir>/vidistill.log.
    Format ends with a trailing newline so consecutive entries are visually
    separated by a blank line in the file.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "vidistill.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s | %(message)s\n",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger("vidistill")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _CONFIGURED = True
