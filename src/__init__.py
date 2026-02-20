"""src package."""

from loguru import logger

# Disable all default log sinks project-wide.
# User will re-introduce logging later with explicit configuration.
logger.remove()
