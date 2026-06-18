"""Polls `docker-compose logs` until the pipeline finishes draining a load-test
run, then writes the full raw logs plus a summary.json with the time series.

Adapted from ams-backend-python-test/results/extract.py for this test's own
failure modes (extraction parsing vs provider) and its own headline metric
(extract attempts per request, not 429/500 counts).

Usage: python extract.py "<label>" <output_dir>
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

POLL_INTERVAL_SECONDS = 20


def docker_logs(service: str) -> str:
    result = subprocess.run(
        ["docker-compose", "logs", service],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout + result.stderr


def count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text))


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: extract.py <label> <output_dir>", file=sys.stderr)
        raise SystemExit(1)

    label, output_dir = sys.argv[1], Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = []
    start = time.monotonic()
    app_log = provider_log = ""

    while True:
        app_log = docker_logs("app")
        provider_log = docker_logs("provider")

        total = count(app_log, r'"POST /v1/requests/[^/]+/process HTTP')
        failed = count(app_log, r"failed to process request")
        failed_extraction = count(app_log, r"extraction\.ExtractionFailed")
        failed_provider = count(app_log, r"provider_client\.(Retryable)?ProviderError")
        extract_attempts = count(provider_log, r'"POST /v1/ai/extract HTTP')
        rate_limited_429 = count(provider_log, r"429 Rate Limit Exceeded")
        sent = total - failed
        done = sent + failed
        elapsed = round(time.monotonic() - start)

        sample = {
            "t": elapsed,
            "total": total,
            "sent": sent,
            "failed": failed,
            "extract_attempts": extract_attempts,
            "rate_limited_429": rate_limited_429,
        }
        samples.append(sample)
        ratio = round(extract_attempts / total, 3) if total else 0
        print(
            f"t+{elapsed}s total={total} sent={sent} failed={failed} "
            f"(extraction={failed_extraction} provider={failed_provider}) "
            f"extract_attempts={extract_attempts} ratio={ratio}",
        )

        if total > 0 and done >= total:
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    (output_dir / "provider.log").write_text(provider_log, encoding="utf-8")
    (output_dir / "app.log").write_text(app_log, encoding="utf-8")

    final = samples[-1]
    summary = {
        "label": label,
        "total_requests": final["total"],
        "drain_seconds": final["t"],
        "final": {
            "sent": final["sent"],
            "failed": final["failed"],
            "failed_extraction": failed_extraction,
            "failed_provider": failed_provider,
            "extract_attempts": final["extract_attempts"],
            "ratio_attempts_per_request": ratio,
            "rate_limited_429": final["rate_limited_429"],
        },
        "samples": samples,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {output_dir}/summary.json, provider.log, app.log")


if __name__ == "__main__":
    main()
