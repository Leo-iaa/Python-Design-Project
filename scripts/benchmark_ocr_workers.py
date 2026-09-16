"""Benchmark worker counts for local OCR indexing on real images."""

import argparse
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from advanced_file_finder.core.filters import filter_directories
from advanced_file_finder.core.ocr.engine import RapidOcrEngine

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def collect_images(root: Path, limit: int) -> list[Path]:
    candidates: list[tuple[int, Path]] = []
    for directory, directories, names in os.walk(root):
        directories[:] = filter_directories(directories)
        for name in names:
            path = Path(directory) / name
            if path.suffix.casefold() not in IMAGE_EXTENSIONS:
                continue
            try:
                with Image.open(path) as image:
                    candidates.append((image.width * image.height, path))
            except (OSError, ValueError):
                continue
    return [path for _, path in sorted(candidates, reverse=True)[:limit]]


def benchmark(paths: list[Path], worker_count: int) -> dict[str, float | int]:
    local = threading.local()

    def recognize(path: Path) -> tuple[bool, int]:
        if not hasattr(local, "engine"):
            local.engine = RapidOcrEngine()
        try:
            result = local.engine.recognize(path)
        except (OSError, ValueError, RuntimeError):
            return False, 0
        return True, len(result.text)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(recognize, paths))
    elapsed = time.perf_counter() - started
    return {
        "workers": worker_count,
        "images": len(paths),
        "total_seconds": round(elapsed, 2),
        "images_per_second": round(len(paths) / elapsed, 3) if elapsed else 0.0,
        "failures": sum(not ok for ok, _ in results),
        "characters": sum(chars for _, chars in results),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2, 4])
    args = parser.parse_args()
    paths = collect_images(args.root, args.count)
    print(f"样本图片：{len(paths)}")
    for worker_count in args.workers:
        print(benchmark(paths, worker_count))


if __name__ == "__main__":
    main()