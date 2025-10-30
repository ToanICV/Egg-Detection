"""Entry point for the State Serial Simulator."""

from .app.controller import AppController


def main() -> None:
    """Start the simulator application."""
    controller = AppController()
    controller.run()


if __name__ == "__main__":
    main()
