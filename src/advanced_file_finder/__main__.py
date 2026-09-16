"""Package entry point."""


def main() -> None:
    """Start the command-line interface."""
    from advanced_file_finder.cli import run_cli

    run_cli()


if __name__ == "__main__":
    main()
