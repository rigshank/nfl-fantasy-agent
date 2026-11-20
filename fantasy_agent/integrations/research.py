"""Tavily research with duplicate caching and real account quota checks."""
import hashlib
import re
from urllib.parse import urlsplit,urlunsplit
import httpx
from tavily import TavilyClient
from ..models import ResearchBundle, ResearchResult


class ProviderUnavailable(RuntimeError):
    pass


def validate_answer_sources(answer,urls):
    def normalized(url):
        p=urlsplit(url.rstrip(".,;"));return urlunsplit((p.scheme,p.netloc,p.path.rstrip("/"),p.query,""))
    allowed={normalized(u) for u in urls}
    unknown={u for u in re.findall(r'https?://[^\s<>\)\]\"\*]+',answer) if normalized(u) not in allowed}
    if unknown:
        raise ProviderUnavailable("Gemini cited a URL that was not returned by a data/research tool. The unchecked answer was withheld; calculations and retrieved sources remain available. Retry with a focused source-backed question.")


def safe_error(exc, *keys):
    detail=getattr(exc,"message",None)
    message=(f"HTTP {exc.code}: " if getattr(exc,"code",None) else "")+detail if isinstance(detail,str) else str(exc)
    for key in keys:
        if key:
            message = message.replace(key, "[REDACTED]")
    return message


class Research:
    PREFERRED_DOMAINS = ["nfl.com", "espn.com", "nbcsports.com", "cbssports.com"]

    def __init__(self, config, store, client=None, usage_client=None):
        self.config, self.store, self.client = config, store, client
        self.usage_client = usage_client

    def account_usage(self):
        key = self.config.tavily_api_key.get_secret_value()
        if not key:
            raise ProviderUnavailable("Tavily API key is missing from environment or deployment secrets.")
        try:
            client = self.usage_client or httpx
            response = client.get("https://api.tavily.com/usage", headers={"Authorization": "Bearer " + key}, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise ProviderUnavailable("Tavily usage check failed: " + safe_error(exc, key) + ". Retry after checking the provider status/key.") from None
        account = data.get("account", {})
        if str(account.get("current_plan", "")).casefold() not in {"researcher", "free"}:
            raise ProviderUnavailable("Tavily account is not on a verified free Researcher plan. No search was sent and no billing settings were changed.")
        if (account.get("paygo_limit") or 0) > 0:
            raise ProviderUnavailable("Tavily pay-as-you-go is enabled. Disable it in Tavily to keep this app free.")
        usage, limit = account.get("plan_usage"), account.get("plan_limit")
        if usage is None or limit is None:
            raise ProviderUnavailable("Tavily did not report the remaining plan allowance; retry its usage endpoint.")
        if usage >= limit:
            raise ProviderUnavailable("Tavily's actual free monthly credits are exhausted. Cached research remains usable; wait for the provider reset.")
        key_usage = data.get("key", {})
        if key_usage.get("limit") is not None and key_usage.get("usage", 0) >= key_usage["limit"]:
            raise ProviderUnavailable("This Tavily API key has reached its provider-configured limit.")
        return data

    def search(self, query, time_range="week"):
        query = " ".join(query.split())
        if not query:
            raise ValueError("Research query is empty.")
        cache_key = "research:v3:" + hashlib.sha256((query.casefold() + str(time_range)).encode()).hexdigest()
        cached = self.store.get(cache_key)
        if cached:
            return ResearchBundle.model_validate(cached[0])
        self.account_usage()
        key = self.config.tavily_api_key.get_secret_value()
        client = self.client or TavilyClient(api_key=key)
        self.store.record_request("tavily")
        try:
            response = client.search(query=query, search_depth="basic", auto_parameters=False,
                topic="news", time_range=time_range, max_results=20,
                include_domains=self.PREFERRED_DOMAINS, include_domains_mode="prefer",
                include_answer=False, include_raw_content=False, include_usage=True,
                include_published_date=True, timeout=45)
        except Exception as exc:
            raise ProviderUnavailable("Tavily search failed: " + safe_error(exc, key) + ". Retry when the provider is available; no paid fallback was used.") from None
        sources, seen = [], set()
        for row in response.get("results", []):
            url = row.get("url", "")
            if urlsplit(url).scheme != "https" or not urlsplit(url).hostname or url in seen:
                continue
            seen.add(url)
            sources.append(ResearchResult(title=row.get("title") or urlsplit(url).hostname,
                url=url, excerpt=row.get("content") or "", published_at=row.get("published_date")))
        bundle = ResearchBundle(query=query, sources=sources)
        self.store.put(cache_key, bundle.model_dump(mode="json"), 14400)
        return bundle

    def search_many(self, queries):
        bundles = [self.search(q) for q in dict.fromkeys(q.strip() for q in queries if q.strip())]
        sources = {s.url: s for b in bundles for s in b.sources}
        return ResearchBundle(query="; ".join(b.query for b in bundles), sources=list(sources.values()))
