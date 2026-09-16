"""Command-line interface, expanded in a later stage."""

import argparse


def run_cli() -> None:
    """Show the application command-line help."""
    parser = argparse.ArgumentParser(prog="advanced-file-finder")
    parser.description = "Advanced File Finder command line interface"
    parser.parse_args()