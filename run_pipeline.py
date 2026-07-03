#!/usr/bin/env python3
"""
run_pipeline.py — SuddWatch Pipeline Entry Point
=================================================
Cron-safe entry point for the flood detection pipeline.
Designed to be called every 12 hours by cron or launchd.

Usage:
    # Run manually
    cd ~/suddwatch && source venv/bin/activate
    python run_pipeline.py

    # Run with verbose logging
    python run_pipeline.py --verbose

    # Dry run (initialise only, no downloads)
    python run_pipeline.py --dry-run

Cron example (every 12 hours):
    0 */12 * * * /Users/billawan/suddwatch/venv/bin/python \
        /Users/billawan/suddwatch/run_pipeline.py \
        >> /Users/billawan/suddwatch/logs/pipeline.log 2>&1
"""

import argparse
import json
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


def parse_args():
    parser = argparse.ArgumentParser(
        description="SuddWatch Flood Detection Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Initialise pipeline and check connectivity without processing scenes",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file (default: logs/pipeline_YYYYMMDD.log)",
    )
    return parser.parse_args()


def setup_log_file(log_file: str = None) -> Path:
    """Create logs directory and return log file path."""
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    if log_file:
        return Path(log_file)
    return log_dir / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"


def main():
    args = parse_args()

    # Set up file logging
    log_path = setup_log_file(args.log_file)
    log_level = logging.DEBUG if args.verbose else logging.INFO

    # File handler — append to daily log
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    ))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("SuddWatch run_pipeline.py starting")
    logger.info(f"Time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Log file: {log_path}")
    logger.info(f"Dry run:  {args.dry_run}")
    logger.info("=" * 60)

    exit_code = 0

    try:
        from src.config import Config
        from src.pipeline import FloodPipeline

        cfg      = Config()
        pipeline = FloodPipeline(cfg)

        if args.dry_run:
            logger.info("Dry run complete — pipeline initialised successfully")
            logger.info("Connectivity checks:")

            # Test alert connectivity
            connectivity = pipeline.alerter.test_connectivity()
            logger.info(f"  Twilio SMS: {'OK' if connectivity['twilio'] else 'FAILED'}")
            logger.info(f"  Gmail SMTP: {'OK' if connectivity['smtp'] else 'FAILED'}")
            if connectivity["errors"]:
                for err in connectivity["errors"]:
                    logger.warning(f"  Error: {err}")

            logger.info("Dry run complete — no scenes processed")
            return 0

        # Run the full pipeline
        results = pipeline.run()

        # Log summary
        logger.info("Pipeline run summary:")
        logger.info(f"  Scenes processed: {len(results.get('scenes_processed', []))}")
        logger.info(f"  Scenes failed:    {len(results.get('scenes_failed', []))}")
        logger.info(f"  Alerts sent:      {results.get('total_alerts_sent', 0)}")
        logger.info(f"  Duration:         {results.get('total_duration_s', 0)}s")
        logger.info(f"  Status:           {results.get('status', 'unknown')}")

        # Write JSON results to logs
        results_path = log_path.parent / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"  Results saved:    {results_path}")

        # Exit code 1 if any scenes failed
        if results.get("scenes_failed"):
            logger.warning(f"{len(results['scenes_failed'])} scene(s) failed")
            exit_code = 1

    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
        exit_code = 130

    except Exception as e:
        logger.error(f"Pipeline crashed: {e}")
        logger.error(traceback.format_exc())
        exit_code = 1

    finally:
        logger.info(f"run_pipeline.py exiting with code {exit_code}")
        logger.info("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
