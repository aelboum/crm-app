"""Workspace settings values (`PHASE2-PLAN.md` S10, §12; decision P2-F 1).

Pure functions: each takes what a client sent and returns the one form the
database stores, or raises `InvalidValue` (whose message names the rule,
never the value). Migration `0004_workspace_settings` checks the same
shapes; these functions also check against the full lists.

- **Locale:** a BCP 47 tag `language[-Script][-REGION]`, normalised to its
  conventional case (`en-gb` -> `en-GB`, `zh-hant-tw` -> `zh-Hant-TW`). It
  drives date and number formatting; the interface itself is English
  first (K5.1).
- **Time zone:** an IANA name known to the runtime (`zoneinfo`). Times are
  stored in UTC; the zone only says how to show them.
- **Currency:** an active ISO 4217 code, upper-cased.
- **Business hours** (decision P5-B): seven days, Monday first, each
  closed (`None`) or one range `{"opens": "HH:MM", "closes": "HH:MM"}` with
  `opens` before `closes`, as wall-clock times in the workspace's zone.
  `None` for the whole week means not set.

Defaults suit the first market (K5: the Netherlands and the EU).
"""

from __future__ import annotations

import re
import zoneinfo
from collections.abc import Mapping, Sequence
from functools import cache

from crm_app.domains.records import InvalidValue
from crm_app.domains.records import email as _email
from crm_app.domains.records import phone as _phone
from crm_app.domains.records import website as _website

DEFAULT_LOCALE = "en"
DEFAULT_TIME_ZONE = "Europe/Amsterdam"
DEFAULT_CURRENCY = "EUR"

_LOCALE = re.compile(r"([a-z]{2,3})(?:-([a-z]{4}))?(?:-([a-z]{2}|[0-9]{3}))?")
_RAW_MAX = 64
_CLOCK = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")
DAYS = 7
# The business's contact details (decision P2-BP).
ADDRESS_MAX = 300
ADDRESS_LINES = 6
_ADDRESS_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")

# Active ISO 4217 currency codes (fund and precious-metal codes left out).
CURRENCIES: frozenset[str] = frozenset(
    [
        "AED",
        "AFN",
        "ALL",
        "AMD",
        "AOA",
        "ARS",
        "AUD",
        "AWG",
        "AZN",
        "BAM",
        "BBD",
        "BDT",
        "BGN",
        "BHD",
        "BIF",
        "BMD",
        "BND",
        "BOB",
        "BRL",
        "BSD",
        "BTN",
        "BWP",
        "BYN",
        "BZD",
        "CAD",
        "CDF",
        "CHF",
        "CLP",
        "CNY",
        "COP",
        "CRC",
        "CUP",
        "CVE",
        "CZK",
        "DJF",
        "DKK",
        "DOP",
        "DZD",
        "EGP",
        "ERN",
        "ETB",
        "EUR",
        "FJD",
        "FKP",
        "GBP",
        "GEL",
        "GHS",
        "GIP",
        "GMD",
        "GNF",
        "GTQ",
        "GYD",
        "HKD",
        "HNL",
        "HTG",
        "HUF",
        "IDR",
        "ILS",
        "INR",
        "IQD",
        "IRR",
        "ISK",
        "JMD",
        "JOD",
        "JPY",
        "KES",
        "KGS",
        "KHR",
        "KMF",
        "KPW",
        "KRW",
        "KWD",
        "KYD",
        "KZT",
        "LAK",
        "LBP",
        "LKR",
        "LRD",
        "LSL",
        "LYD",
        "MAD",
        "MDL",
        "MGA",
        "MKD",
        "MMK",
        "MNT",
        "MOP",
        "MRU",
        "MUR",
        "MVR",
        "MWK",
        "MXN",
        "MYR",
        "MZN",
        "NAD",
        "NGN",
        "NIO",
        "NOK",
        "NPR",
        "NZD",
        "OMR",
        "PAB",
        "PEN",
        "PGK",
        "PHP",
        "PKR",
        "PLN",
        "PYG",
        "QAR",
        "RON",
        "RSD",
        "RUB",
        "RWF",
        "SAR",
        "SBD",
        "SCR",
        "SDG",
        "SEK",
        "SGD",
        "SHP",
        "SLE",
        "SOS",
        "SRD",
        "SSP",
        "STN",
        "SVC",
        "SYP",
        "SZL",
        "THB",
        "TJS",
        "TMT",
        "TND",
        "TOP",
        "TRY",
        "TTD",
        "TWD",
        "TZS",
        "UAH",
        "UGX",
        "USD",
        "UYU",
        "UZS",
        "VES",
        "VND",
        "VUV",
        "WST",
        "XAF",
        "XCD",
        "XCG",
        "XOF",
        "XPF",
        "YER",
        "ZAR",
        "ZMW",
        "ZWG",
    ]
)


@cache
def _time_zones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones())


def _bounded(value: str) -> str:
    if len(value) > _RAW_MAX or "\x00" in value:
        raise InvalidValue("is not valid")
    return value.strip()


def locale(value: str) -> str:
    match = _LOCALE.fullmatch(_bounded(value).lower())
    if match is None:
        raise InvalidValue("must be a language tag such as en or nl-NL")
    language, script, region = match.groups()
    parts = [language]
    if script:
        parts.append(script.title())
    if region:
        parts.append(region.upper())
    return "-".join(parts)


def time_zone(value: str) -> str:
    zone = _bounded(value)
    if zone not in _time_zones():
        raise InvalidValue("must be a time zone such as Europe/Amsterdam")
    return zone


def currency(value: str) -> str:
    code = _bounded(value).upper()
    if code not in CURRENCIES:
        raise InvalidValue("must be an ISO 4217 currency code such as EUR")
    return code


def _clock(value: object) -> str:
    if not isinstance(value, str) or _CLOCK.fullmatch(value) is None:
        raise InvalidValue("must give times as HH:MM, 00:00 to 23:59")
    return value


def business_hours(
    value: Sequence[Mapping[str, object] | None] | None,
) -> list[dict[str, str] | None] | None:
    """Seven days, Monday first; each `None` or one range within the day."""
    if value is None:
        return None
    if len(value) != DAYS:
        raise InvalidValue("must give seven days, Monday first")
    week: list[dict[str, str] | None] = []
    for day in value:
        if day is None:
            week.append(None)
            continue
        if set(day) != {"opens", "closes"}:
            raise InvalidValue("must give each open day an opening and a closing time")
        opens, closes = _clock(day["opens"]), _clock(day["closes"])
        # Zero-padded HH:MM strings sort as the times they name.
        if not opens < closes:
            raise InvalidValue("must close after it opens on the same day")
        week.append({"opens": opens, "closes": closes})
    return week


# --- The business's contact details (decision P2-BP) --------------------------------
# Each returns `None` for an empty value, which clears the field.


def business_phone(value: str) -> str | None:
    return _phone(value)


def business_email(value: str) -> str | None:
    return _email(value)


def business_website(value: str) -> str | None:
    return _website(value)


def business_address(value: str) -> str | None:
    """A postal address as entered: line breaks as LF, each line trimmed,
    empty lines dropped, at most 6 lines and 300 characters, no control
    characters other than the line breaks."""
    if "\x00" in value:
        raise InvalidValue("must not contain control characters")
    lines = [line.strip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    kept = [line for line in lines if line]
    if not kept:
        return None
    address = "\n".join(kept)
    if _ADDRESS_CONTROL.search(address):
        raise InvalidValue("must not contain control characters")
    if len(kept) > ADDRESS_LINES:
        raise InvalidValue(f"must be at most {ADDRESS_LINES} lines")
    if len(address) > ADDRESS_MAX:
        raise InvalidValue(f"must be at most {ADDRESS_MAX} characters")
    return address
