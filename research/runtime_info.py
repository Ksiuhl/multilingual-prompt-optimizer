"""Non-secret local runtime provenance for reproducible experiment records."""

import json
import platform
from datetime import datetime, timezone
from urllib.request import ProxyHandler, build_opener

from multilingual_prompt_optimizer import __version__


def local_runtime():
    client = build_opener(ProxyHandler({}))

    def get(path):
        with client.open("http://127.0.0.1:11434" + path, timeout=10) as response:
            return json.load(response)

    return {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "optimizer_version": __version__,
        "python_version": platform.python_version(),
        "ollama_version": get("/api/version")["version"],
        "models": [
            {k: m[k] for k in ("name", "digest", "size", "details")}
            for m in get("/api/tags")["models"]
        ],
    }
