"""Website integration rules (decision P12-W): pure, no database or framework.

A workspace lists the websites (WordPress, Shopify, Webflow, Wix or any
other) whose pages may send leads into it, each with its allowed origins.
A browser sends the page's `Origin` with every cross-site request; the
public form routes accept a cross-site submission only when that origin is
allowed for an active website of the form's workspace, and answer it with
CORS headers naming that origin alone. Listing an origin lets that site
put leads into this workspace and nothing else, so it needs no proof of
ownership: a workspace that lists someone else's site only receives that
site's leads if the site itself embeds this workspace's form.

Attribution (UTM parameters, the page and the referrer) is optional, kept
short, and a page URL from another origin than the request's is dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from crm_app.domains.records import InvalidValue

ORIGINS_MAX = 20
NAME_MAX = 120
ATTRIBUTION_MAX = 300
URL_MAX = 2000
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST = re.compile(rf"{_LABEL}(?:\.{_LABEL})*")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_LOCAL_HOSTS = ("localhost", "127.0.0.1")
_ORIGIN_RULE = "origin: a site address such as https://www.example.com"


def origin(value: str, *, allow_local: bool = False) -> str:
    """An origin in canonical form, `https://host[:port]`, or
    `InvalidValue`. No path, query, fragment, credentials or wildcard;
    `http` only for localhost when `allow_local` (development)."""
    text = value.strip().lower().rstrip("/")
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise InvalidValue(_ORIGIN_RULE) from None
    host = parts.hostname or ""
    local = host in _LOCAL_HOSTS
    if (
        parts.scheme not in ("https", "http")
        or (parts.scheme == "http" and not (allow_local and local))
        or parts.username
        or parts.password
        or parts.path
        or parts.query
        or parts.fragment
        or "*" in text
        or not (_HOST.fullmatch(host) and ("." in host or (local and allow_local)))
        or (local and not allow_local)
    ):
        raise InvalidValue(_ORIGIN_RULE)
    default = 443 if parts.scheme == "https" else 80
    return f"{parts.scheme}://{host}" + (f":{port}" if port and port != default else "")


def origins(values: list[str], *, allow_local: bool = False) -> list[str]:
    """Distinct canonical origins, at least one and at most `ORIGINS_MAX`."""
    found: list[str] = []
    for value in values:
        canonical = origin(value, allow_local=allow_local)
        if canonical not in found:
            found.append(canonical)
    if not 1 <= len(found) <= ORIGINS_MAX:
        raise InvalidValue(f"origins: 1 to {ORIGINS_MAX} site addresses")
    return found


def request_origin(header: str | None) -> str | None:
    """The canonical form of a request's `Origin` header, or None when it
    is absent, `null` or not an origin."""
    if not header or header.strip() == "null":
        return None
    try:
        return origin(header, allow_local=True)
    except InvalidValue:
        return None


def name(value: str) -> str:
    text = " ".join(value.split())
    if not 1 <= len(text) <= NAME_MAX or _CONTROL.search(text):
        raise InvalidValue(f"name: 1 to {NAME_MAX} characters")
    return text


@dataclass(frozen=True)
class Attribution:
    utm: dict[str, str]
    page_url: str | None
    referrer: str | None

    def as_dict(self) -> dict[str, object]:
        return {**self.utm, "page_url": self.page_url, "referrer": self.referrer}

    @property
    def empty(self) -> bool:
        return not self.utm and self.page_url is None and self.referrer is None


def _short(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(_CONTROL.sub(" ", value).split())[:ATTRIBUTION_MAX]
    return text or None


def _url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > URL_MAX or _CONTROL.search(value):
        return None
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return None
    if parts.scheme not in ("https", "http") or not parts.hostname:
        return None
    return value.strip()


def page_origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def attribution(raw: object, request: str | None) -> Attribution:
    """The attribution kept for a submission. Unknown keys are ignored; a
    page URL is kept only when it is on the request's own origin."""
    if not isinstance(raw, dict):
        return Attribution({}, None, None)
    utm = {key: text for key in UTM_KEYS if (text := _short(raw.get(key))) is not None}
    page = _url(raw.get("page_url"))
    if page is not None and (request is None or request_origin(page_origin(page)) != request):
        page = None
    return Attribution(utm, page, _url(raw.get("referrer")))
