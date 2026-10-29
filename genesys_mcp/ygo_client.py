"""Thin client over the YGOPRODeck v7 card API, with on-disk caching and throttling."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

API_URL = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
ARCHETYPES_URL = "https://db.ygoprodeck.com/api/v7/archetypes.php"

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_TTL_SECONDS = 24 * 60 * 60

# Published limit is 20 req/s; exceeding it blocks the IP for an hour.
MIN_REQUEST_INTERVAL = 0.2


class YgoApiError(RuntimeError):
    """The API rejected the request and explained why."""

    def __init__(self, message: str, params: dict[str, Any]):
        super().__init__(message)
        self.api_message = message
        self.params = params


class YgoClient:
    def __init__(self, cache_dir: Path | None = None, ttl: int = CACHE_TTL_SECONDS):
        self._cache_dir = cache_dir or CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    def _cache_path(self, url: str, params: dict[str, Any]) -> Path:
        key = json.dumps([url, sorted(params.items())], sort_keys=True)
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self._cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path) -> Any | None:
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self._ttl:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    async def _throttle(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < MIN_REQUEST_INTERVAL:
                await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
            self._last_request = time.monotonic()

    async def _get(self, url: str, params: dict[str, Any]) -> Any:
        cache_path = self._cache_path(url, params)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached

        await self._throttle()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)

        if response.status_code == 400:
            try:
                message = response.json().get("error", response.text)
            except json.JSONDecodeError:
                message = response.text
            raise YgoApiError(message, params)

        if response.status_code == 429:
            raise YgoApiError(
                "Rate limited by YGOPRODeck. The published limit is 20 requests per "
                "second and exceeding it blocks the IP for an hour.",
                params,
            )

        response.raise_for_status()
        payload = response.json()
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    async def cards(self, **params: Any) -> list[dict[str, Any]]:
        payload = await self._get(API_URL, params)
        return payload.get("data", [])

    async def archetypes(self) -> list[str]:
        payload = await self._get(ARCHETYPES_URL, {})
        return [row["archetype_name"] for row in payload]