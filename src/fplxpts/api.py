"""Thin client for the public (unofficial, undocumented) Fantasy Premier League API, with an on-disk cache.

Be polite: the cache means repeated runs do not hit the API. Do not commit the cache directory.
"""
from __future__ import annotations

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://fantasy.premierleague.com/api/"
UA = {"User-Agent": "Mozilla/5.0 (fplxpts research project)"}


class FPLClient:
    def __init__(self, cache_dir: str | Path = ".cache", ttl: int = 3600, workers: int = 6):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.ttl, self.workers = ttl, workers

    def _fetch(self, path: str, tries: int = 4):
        for i in range(tries):
            try:
                req = urllib.request.Request(BASE + path, headers=UA)
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())
            except Exception:
                if i == tries - 1:
                    raise
                time.sleep(1.5 * (i + 1))

    def get(self, path: str, ttl: int | None = None):
        f = self.cache / (path.strip("/").replace("/", "_") + ".json")
        ttl = self.ttl if ttl is None else ttl
        if f.exists() and time.time() - f.stat().st_mtime < ttl:
            return json.loads(f.read_text())
        data = self._fetch(path)
        f.write_text(json.dumps(data))
        return data

    def bootstrap(self):
        return self.get("bootstrap-static/")

    def fixtures(self):
        return self.get("fixtures/")

    def element_summary(self, pid: int):
        return self.get(f"element-summary/{pid}/")

    def element_summaries(self, ids) -> dict:
        with ThreadPoolExecutor(self.workers) as ex:
            return dict(zip(ids, ex.map(self.element_summary, ids)))
