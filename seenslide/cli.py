"""Command-line interface for SeenSlide."""

import logging
import argparse
import sys
import time
from pathlib import Path

from seenslide.orchestrator import SeenSlideOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cmd_start(args):
    """Start a capture session.

    Args:
        args: Parsed command-line arguments
    """
    orchestrator = SeenSlideOrchestrator(config_path=args.config)

    # Start session
    success = orchestrator.start_session(
        session_name=args.name,
        description=args.description or "",
        presenter_name=args.presenter or "",
        monitor_id=args.monitor
    )

    if not success:
        logger.error("Failed to start session")
        sys.exit(1)

    logger.info(f"Session '{args.name}' started successfully")
    logger.info("Press Ctrl+C to stop...")

    try:
        # Keep running until interrupted
        while True:
            time.sleep(1)

            # Print statistics periodically
            if args.verbose:
                stats = orchestrator.get_statistics()
                if stats.get("capture"):
                    logger.info(f"Captured: {stats['capture']['captures_count']} frames")
                if stats.get("storage"):
                    logger.info(f"Stored: {stats['storage']['slides_stored']} slides")

    except KeyboardInterrupt:
        logger.info("\nStopping session...")
        orchestrator.stop_session()
        logger.info("Session stopped")


def cmd_server(args):
    """Start the web server.

    Args:
        args: Parsed command-line arguments
    """
    from modules.server.app import SlideServer

    logger.info(f"Starting web server on {args.host}:{args.port}")

    # Get storage path from config if available
    storage_path = "/tmp/seenslide"  # Default
    if args.config:
        from core.config.config_loader import ConfigLoader
        config_loader = ConfigLoader()
        config = config_loader.load_from_file(args.config)
        storage_config = config.get("storage", {}).get("config", {})
        storage_path = storage_config.get("base_path", "/tmp/seenslide")

    server = SlideServer(
        storage_path=storage_path,
        host=args.host,
        port=args.port
    )
    server.run()


def cmd_gui(args):
    """Start the admin GUI.

    Args:
        args: Parsed command-line arguments
    """
    from modules.admin.app import main as gui_main

    logger.info("Starting admin GUI")
    gui_main(config_path=args.config)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SeenSlide - Real-time slide navigation system",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Global options
    parser.add_argument(
        "--config",
        help="Path to configuration file"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    # Subcommands
    subparsers = parser.add_subparsers(
        title="commands",
        description="Available commands",
        dest="command"
    )

    # Start command
    start_parser = subparsers.add_parser(
        "start",
        help="Start a capture session"
    )
    start_parser.add_argument(
        "name",
        help="Session name"
    )
    start_parser.add_argument(
        "--description",
        help="Session description"
    )
    start_parser.add_argument(
        "--presenter",
        help="Presenter name"
    )
    start_parser.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="Monitor ID to capture (default: 1)"
    )
    start_parser.set_defaults(func=cmd_start)

    # Server command
    server_parser = subparsers.add_parser(
        "server",
        help="Start the web server"
    )
    server_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    server_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)"
    )
    server_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    server_parser.set_defaults(func=cmd_server)

    # GUI command
    gui_parser = subparsers.add_parser(
        "gui",
        help="Start the admin GUI"
    )
    gui_parser.set_defaults(func=cmd_gui)

    # Parse arguments
    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Execute command
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
