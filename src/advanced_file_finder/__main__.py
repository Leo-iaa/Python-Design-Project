"""Dispatch to CLI when arguments are supplied, otherwise launch the GUI."""

import sys

from advanced_file_finder.cli import run_cli
from advanced_file_finder.gui.main_window import run


def main() -> None:
    """Start the appropriate application interface."""
    if len(sys.argv) > 1:
        run_cli()
    else:
        run()


if __name__ == "__main__":
    main()
