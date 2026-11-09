"""Map-reduce research: parallel asyncio workers, single-flight fetching, dedup and a cited report."""

from .dedup import deduplicate
from .models import Cluster, Finding, Plan, Report, SubQuestion
from .swarm import Swarm

__version__ = "0.2.0"

__all__ = ["deduplicate", "Cluster", "Finding", "Plan", "Report", "SubQuestion", "Swarm"]
