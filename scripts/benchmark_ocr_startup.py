"""Measure real RapidOCR cold-process and warm inference timings."""

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path


def child(image: Path) -> None:
    process = time.perf_counter()
    import_started = time.perf_counter()
    from advanced_file_finder.core.ocr.engine import RapidOcrEngine

    imported = time.perf_counter()
    engine_started = time.perf_counter()
    engine = RapidOcrEngine()
    initialized = time.perf_counter()
    engine.recognize(image)
    first = time.perf_counter()
    engine.recognize(image)
    second = time.perf_counter()
    print(
        json.dumps(
            {
                "process_startup": import_started - process,
                "import": imported - import_started,
                "engine_init": initialized - engine_started,
                "first_ocr": first - initialized,
                "second_ocr": second - first,
            },
            separators=(",", ":"),
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    if args.child:
        child(args.image)
        return
    samples = []
    for _ in range(max(3, args.runs)):
        result = subprocess.run(
            [sys.executable, __file__, str(args.image), "--child"],
            capture_output=True,
            text=True,
            check=True,
        )
        samples.append(json.loads(result.stdout.strip()))
    keys = samples[0].keys()
    summary = {
        key: {
            "min": min(x[key] for x in samples),
            "median": statistics.median(x[key] for x in samples),
            "max": max(x[key] for x in samples),
        }
        for key in keys
    }
    reports = Path(__file__).resolve().parents[1] / ".local" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "ocr_startup_benchmark.md").write_text(
        "# OCR Startup Benchmark\n\n"
        + "\n".join(
            f"- {key}: min {value['min']:.3f}s / median {value['median']:.3f}s / max {value['max']:.3f}s"
            for key, value in summary.items()
        )
        + f"\n\nRuns: {len(samples)}\n",
        encoding="utf-8",
    )
    print(json.dumps({"runs": len(samples), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
