"""Command line entry: an agent shops on a local website it has never seen, by reading the accessibility tree.

    python demo.py                    # compact trace
    python demo.py --show-snapshots   # print every snapshot the model sees
"""

from __future__ import annotations

import argparse

from .agent import BrowserAgent
from .browser import Browser
from .config import Settings, load_settings
from .llm import make_llm
from .site import ShopSite
from .trace import Trace

GOAL = "Buy 2 Blue Ceramic Mugs with standard shipping for Ada Lovelace (ada@example.com)"


def run(goal: str, settings: Settings, max_steps: int, show_snapshots: bool = False) -> tuple[str, ShopSite]:
    """Run one shopping goal against a fresh simulated shop; return the agent's answer and the site."""
    trace = Trace()
    site = ShopSite(settings.site_dir)
    llm = make_llm(settings)
    trace.box(f"Browser agent  |  site: http://{site.host} (simulated, offline)  |  model: {llm.name}")
    agent = BrowserAgent(Browser(site), llm, max_steps=max_steps, trace=trace, show_snapshots=show_snapshots)
    answer = agent.run(goal)
    if site.orders:
        order = site.orders[-1]
        trace.box("SERVER SIDE: what the shop actually received", [
            f"order {order['number']}: {order['items']}, total ${order['total']:.2f}, ship {order['shipping']}",
            f"customer: {order['name']} <{order['email']}>, terms accepted: {order['terms']}"])
    return answer, site


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Browser automation agent over an accessibility snapshot")
    parser.add_argument("--goal", default=GOAL)
    parser.add_argument("--show-snapshots", action="store_true")
    parser.add_argument("--max-steps", type=int, default=settings.max_steps)
    args = parser.parse_args(argv)
    run(args.goal, settings, args.max_steps, args.show_snapshots)
    return 0
