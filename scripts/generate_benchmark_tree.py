"""Generate bounded, zero-content benchmark trees under .local."""

import argparse
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--files", type=int, default=1000)
    p.add_argument("--dirs", type=int, default=10)
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--output", type=Path, default=Path(".local/benchmark_data"))
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    dirs = [a.output]
    for i in range(max(0, a.dirs)):
        current = a.output / f"dir_{i % max(1, a.dirs // max(1, a.depth))}"
        current.mkdir(parents=True, exist_ok=True)
        dirs.append(current)
    for i in range(a.files):
        (dirs[i % len(dirs)] / f"report_{i:06d}.txt").touch()
    print(f"generated {a.files} files in {len(dirs)} directories at {a.output}")


if __name__ == "__main__":
    main()
