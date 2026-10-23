"""Values of contact and company records (`PHASE3-PLAN.md` §19.4, §19.6).

Pure functions: each takes what a client sent and returns the one form the
database stores, or raises `InvalidValue`. The API validates with them, so
a value is normalised exactly once and the same way on create and update;
the migration's `CHECK`s accept exactly these forms, so the partial unique
indexes compare like with like (decision P3-A 3).

Messages name the rule, never the value: they reach responses.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

STAGES = ("lead", "prospect", "customer", "inactive")
SOURCES = ("manual", "import", "form", "referral", "other")
# Users may choose only these sources; `import` and `form` are set by the
# system in later slices (decision P3-A 2).
USER_SOURCES = ("manual", "referral", "other")

NAME_MAX = 200
EMAIL_MAX = 320
PHONE_MAX = 32
JOB_TITLE_MAX = 200
CITY_MAX = 100
INDUSTRY_MAX = 100
WEBSITE_MAX = 2048
DOMAIN_MAX = 253

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE = re.compile(r"\+?[0-9(][0-9 ()./-]*")
_DOMAIN = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")
_COUNTRY = re.compile(r"[A-Z]{2}")


class InvalidValue(ValueError):
    """A value outside the rules; the message names the rule only."""


def text(value: str | None, maximum: int, *, required: bool = False) -> str | None:
    """Trimmed text of 1..maximum characters. Optional text that is empty
    after trimming becomes `None`, never ''."""
    trimmed = value.strip() if value is not None else ""
    if not trimmed:
        if required:
            raise InvalidValue("is required")
        return None
    if len(trimmed) > maximum:
        raise InvalidValue(f"must be at most {maximum} characters")
    return trimmed


def email(value: str | None) -> str | None:
    """Trimmed and lower-cased as a whole: the form the unique index compares."""
    trimmed = text(value, EMAIL_MAX)
    if trimmed is None:
        return None
    normalised = trimmed.lower()
    if not _EMAIL.fullmatch(normalised):
        raise InvalidValue("must be an email address")
    return normalised


def phone(value: str | None) -> str | None:
    """Stored as entered (trimmed): digits, an optional leading +, spaces and
    ( ) . / - separators. No E.164 conversion in slice 3A."""
    trimmed = text(value, PHONE_MAX)
    if trimmed is None:
        return None
    if not _PHONE.fullmatch(trimmed) or sum(c.isdigit() for c in trimmed) < 3:
        raise InvalidValue("must be a phone number")
    return trimmed


def website(value: str | None) -> str | None:
    """An absolute `http` or `https` URL with a host; nothing is fetched."""
    trimmed = text(value, WEBSITE_MAX)
    if trimmed is None:
        return None
    parts = urlsplit(trimmed)
    if (
        any(c.isspace() for c in trimmed)
        or parts.scheme.lower() not in {"http", "https"}
        or not parts.hostname
    ):
        raise InvalidValue("must be an http or https URL")
    return trimmed


def domain(value: str | None) -> str | None:
    """Lower-case host name in ASCII: trimmed, trailing dot and leading
    `www.` removed, internationalised names IDNA-encoded."""
    trimmed = text(value, DOMAIN_MAX)
    if trimmed is None:
        return None
    host = trimmed.lower().rstrip(".").removeprefix("www.")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise InvalidValue("must be a domain name") from None
    # The last label needs a letter, so an IP address is not a domain.
    top = host.rsplit(".", 1)[-1]
    if len(host) > DOMAIN_MAX or not _DOMAIN.fullmatch(host) or top.isdigit():
        raise InvalidValue("must be a domain name")
    return host


def domain_from_website(url: str | None) -> str | None:
    """The normalised domain of a validated website, or `None` when its host
    is not a domain name (for example an IP address)."""
    if url is None:
        return None
    try:
        return domain(urlsplit(url).hostname)
    except InvalidValue:
        return None


def country_code(value: str | None) -> str | None:
    """Two letters, stored upper-case (ISO 3166-1 alpha-2 shape; membership
    of the ISO list is not checked)."""
    trimmed = text(value, 2)
    if trimmed is None:
        return None
    upper = trimmed.upper()
    if not _COUNTRY.fullmatch(upper):
        raise InvalidValue("must be a two-letter country code")
    return upper


def stage(value: str) -> str:
    if value not in STAGES:
        raise InvalidValue(f"must be one of {', '.join(STAGES)}")
    return value


def user_source(value: str) -> str:
    if value not in USER_SOURCES:
        raise InvalidValue(f"must be one of {', '.join(USER_SOURCES)}")
    return value
