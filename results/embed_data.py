"""Copies the real summary.json files verbatim into dashboard.html so it can
be opened directly (file://) with no server. The JSON files stay in place as
the source of truth; this only embeds their parsed content, byte for byte.

Adapted from ams-backend-python-test/results/embed_data.py. To add a
comparison run later: drop its summary.json in a new results/<name>/ folder,
add <name> to RUN_DIRS below, and re-run this script.

Usage: python embed_data.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
DASHBOARD = HERE / "dashboard.html"
MARKER_START = "<!-- EMBEDDED_DATA_START -->"
MARKER_END = "<!-- EMBEDDED_DATA_END -->"
RUN_DIRS = ("layered-extraction",)


def main() -> None:
    data = {
        name: json.loads((HERE / name / "summary.json").read_text(encoding="utf-8"))
        for name in RUN_DIRS
    }

    block = (
        f"{MARKER_START}\n"
        f"<script>window.__EMBEDDED_RESULTS__ = {json.dumps(data)};</script>\n"
        f"{MARKER_END}"
    )

    html = DASHBOARD.read_text(encoding="utf-8")
    start = html.index(MARKER_START)
    end = html.index(MARKER_END) + len(MARKER_END)
    html = html[:start] + block + html[end:]
    DASHBOARD.write_text(html, encoding="utf-8")

    total_samples = sum(len(v["samples"]) for v in data.values())
    print(f"embedded {len(data)} run(s) ({total_samples} samples) into {DASHBOARD}")


if __name__ == "__main__":
    main()
