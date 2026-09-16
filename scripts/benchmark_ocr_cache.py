"""Benchmark SQLite OCR cache operations using mock metadata (not real OCR)."""

import statistics
import time
from pathlib import Path

from advanced_file_finder.core.ocr.cache import OcrCache
from advanced_file_finder.core.ocr.engine import OcrResult


def main() -> None:
    root = Path(__file__).resolve().parents[1] / ".local" / "cache_benchmark"
    root.mkdir(parents=True, exist_ok=True)
    cache = OcrCache(root / "ocr.sqlite")
    files = []
    for i in range(1000):
        path = root / f"{i}.png"
        path.write_bytes(b"x")
        files.append(path)
        cache.upsert(path, OcrResult("benchmark text", 0.8))
    times = []
    for _ in range(5):
        started = time.perf_counter()
        [cache.get(path) for path in files]
        times.append(time.perf_counter() - started)
    report = Path(__file__).resolve().parents[1] / ".local" / "reports"
    report.mkdir(parents=True, exist_ok=True)
    (report / "ocr_cache_benchmark.md").write_text(
        f"# OCR Cache Benchmark\n\n1000 cached metadata entries (no OCR inference).\n\n- median lookup pass: {statistics.median(times):.4f}s\n- min: {min(times):.4f}s\n- max: {max(times):.4f}s\n",
        encoding="utf-8",
    )
    print(f"1000 cached metadata entries: median {statistics.median(times):.4f}s")


if __name__ == "__main__":
    main()
