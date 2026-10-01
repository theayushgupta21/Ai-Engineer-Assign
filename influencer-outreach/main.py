"""CLI orchestration for the influencer outreach pipeline."""
from __future__ import annotations

import argparse

from src.config import load_config
from src.discovery import discover_channels
from src.enrichment import enrich_channels
from src.filtering import filter_influencers
from src.personalize import personalize_messages
from src.sender import send_outreach
from src.utils.logger import get_logger


def main() -> None:
    """Parse a stage command and run the requested pipeline step."""
    parser = argparse.ArgumentParser(description="YouTube influencer outreach pipeline")
    parser.add_argument("stage", choices=("run-all", "discover", "enrich", "filter", "personalize", "send"))
    parser.add_argument("--live", action="store_true", help="Send approved drafts to TEST_INBOX")
    args = parser.parse_args()
    config = load_config()
    logger = get_logger("main", config["paths"]["log_file"])
    stages = {
        "discover": lambda: discover_channels(config),
        "enrich": lambda: enrich_channels(config),
        "filter": lambda: filter_influencers(config),
        "personalize": lambda: personalize_messages(config),
        "send": lambda: send_outreach(config, live=args.live),
    }
    requested = ("discover", "enrich", "filter", "personalize", "send") if args.stage == "run-all" else (args.stage,)
    for stage in requested:
        logger.info("Starting stage: %s", stage)
        stages[stage]()
        logger.info("Finished stage: %s", stage)


if __name__ == "__main__":
    main()