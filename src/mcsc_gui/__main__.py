"""Module entry point for the project CLI."""

from .main import ServerCreatorGUI


def main() -> None:
    """Run the application window."""
    ServerCreatorGUI().run()


if __name__ == "__main__":
    main()
