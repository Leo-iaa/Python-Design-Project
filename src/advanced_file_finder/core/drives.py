"""Platform-aware discovery of available search roots."""

import os
from pathlib import Path


def available_drives() -> tuple[Path, ...]:
    """Return mounted Windows drives, or the POSIX root on other platforms."""
    if os.name != "nt":
        return (Path("/"),)
    return tuple(
        Path(f"{letter}:/")
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        if Path(f"{letter}:/").exists()
    )
