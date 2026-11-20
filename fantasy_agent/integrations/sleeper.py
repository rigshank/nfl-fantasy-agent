import random
import re
import time
from urllib.parse import quote
import httpx

from ..storage import Store


class DataUnavailable(RuntimeError):
    pass


class Sleeper:
    BASE = "https://api.sleeper.app/v1"

    def __init__(self, store: Store, client=None):
        self.store = store
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)

    def get(self, path: str, ttl=300, force=False):
        cached = self.store.get("sleeper:" + path)
        if cached and not force:
            return cached
        for attempt in range(3):
            # Shared local ceiling comfortably below Sleeper's documented limit.
            self.store.reserve("sleeper", [(time.time() - 60, 999)])
            try:
                response = self.client.get(self.BASE + path)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        try:
                            delay = float(response.headers.get("Retry-After", 2 ** attempt))
                        except ValueError:
                            delay = 2 ** attempt
                        time.sleep(min(max(delay, 0), 5) + random.uniform(0, .2))
                        continue
                response.raise_for_status()
                data = response.json()
                if data is None:
                    raise DataUnavailable("Sleeper returned no data. Check username or league ID.")
                self.store.put("sleeper:" + path, data, ttl)
                return self.store.get("sleeper:" + path)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise DataUnavailable("Sleeper connection failed after three attempts.") from None
            except httpx.HTTPStatusError as exc:
                raise DataUnavailable(f"Sleeper HTTP {exc.response.status_code} {exc.response.reason_phrase} for {path}. Check the identifier or retry after the provider recovers.") from None
            except ValueError as exc:
                raise DataUnavailable(f"Sleeper returned invalid JSON for {path}: {exc}. Retry the refresh; no substitute data was used.") from None
        raise DataUnavailable("Sleeper is temporarily unavailable.")

    def user(self, username):
        if not re.fullmatch(r"[\w.-]{1,64}", username):
            raise ValueError("Enter a Sleeper username or user ID, not a URL.")
        return self.get("/user/" + quote(username, safe=""))[0]

    def leagues(self, uid, season):
        return self.get(f"/user/{quote(str(uid), safe='')}/leagues/nfl/{int(season)}")[0]

    def state(self):
        return self.get("/state/nfl", ttl=300)[0]

    def catalog(self):
        # NEVER bypass the daily player cache when refreshing a league.
        return self.get("/players/nfl", ttl=86400)
