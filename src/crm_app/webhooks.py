"""Outbound webhooks for customers (decision P12-H).

Owners and Admins add HTTPS endpoints in Settings > Integrations; the
signing secret is shown once. SaaS-OS's `core.webhooks` does the rest:
the secret is kept encrypted, every delivery is signed (`X-Webhook-
Signature`: `sha256=` HMAC over `"<X-Webhook-Timestamp>." + body`), sent
only through the worker's egress proxy, refused for a private address at
every attempt, retried with backoff and then dead-lettered. Delivery is
recorded in SaaS-OS's outbox in the same transaction as the change, so a
rolled-back change sends nothing.

Events (`EVENTS`), emitted where automations start for the same moment:
`contact.created` (never for an import), `contact.updated`,
`deal.stage_changed` (a member's move, not a stage removal),
`form.submitted` and `appointment.booked`. The data is kept small
(decision P12-H C): record IDs, and for contacts the name, email,
lifecycle stage and source; `contact.updated` names the changed fields,
not their values. Every endpoint receives every event: SaaS-OS has no
per-subscription filter (gap 19).

Delivery history reads SaaS-OS's outbox rows for an endpoint: event,
status, attempts, times and the last error; never the payload.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from saas_os.core.authority import UserCaller
from saas_os.core.crypto import EncryptionError
from saas_os.core.outbox import OutboxEvent
from saas_os.core.webhooks import (
    InvalidWebhookUrlError,
    WebhookSubscriptionNotFoundError,
    list_subscriptions,
    subscribe,
    trigger_event,
    unsubscribe,
)
from saas_os.infra.db import Session, select, tenant_session_scope

from crm_app.records import RecordError, RecordNotFoundError, Scope

EVENTS = (
    "contact.created",
    "contact.updated",
    "deal.stage_changed",
    "form.submitted",
    "appointment.booked",
)
MAX_ENDPOINTS = 10
URL_MAX = 2000
HISTORY = 20
ERROR_MAX = 200

Item = dict[str, Any]


class WebhookError(RecordError):
    status, code = 422, "invalid_webhook_url"


class WebhooksUnavailableError(RecordError):
    """The member, or this workspace's roles, lack SaaS-OS's webhook
    permissions (a workspace created before P12-K)."""

    status, code = 403, "integrations_unavailable"


class WebhookLimitError(RecordError):
    status, code = 409, "webhook_limit"


class WebhookKeyMissingError(RecordError):
    """The deployment has no field-encryption key, which SaaS-OS needs to
    keep a signing secret (`FIELD_ENCRYPTION_ACTIVE_KEY_VERSION`,
    `FIELD_ENCRYPTION_KEY_<VERSION>`)."""

    status, code = 503, "webhooks_not_configured"


def _shown(url: str) -> str:
    """The address without its query or fragment, which may carry a token
    the receiving service issued."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _plain(value: object) -> object:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def emit(session: Session, workspace: uuid.UUID, event: str, data: Mapping[str, object]) -> None:
    """Record `event` for every endpoint of `workspace`, in the caller's
    tenant session and transaction. Nothing happens without endpoints."""
    if event not in EVENTS:
        raise ValueError(f"unknown webhook event {event!r}")
    trigger_event(session, workspace, event, {key: _plain(v) for key, v in data.items()})


def contact_data(contact: Any) -> dict[str, object]:
    """The contact fields an event carries (P12-H C), nothing else."""
    return {
        "id": contact.id,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "email": contact.email,
        "lifecycle_stage": contact.lifecycle_stage,
        "source": contact.source,
    }


def _deliveries(session: Session, workspace: uuid.UUID, endpoint: uuid.UUID) -> list[Item]:
    rows = session.execute(
        select(OutboxEvent)
        .where(
            OutboxEvent.tenant_id == workspace,
            OutboxEvent.aggregate_type == "webhook_subscription",
            OutboxEvent.aggregate_id == str(endpoint),
        )
        .order_by(OutboxEvent.created_at.desc(), OutboxEvent.id.desc())
        .limit(HISTORY)
    ).scalars()
    return [
        {
            "id": row.id,
            "event": str((row.payload or {}).get("event_type", "")),
            "status": row.status,
            "attempts": row.attempts,
            "created_at": row.created_at,
            "published_at": row.published_at,
            "last_error": (row.last_error or "")[:ERROR_MAX] or None,
        }
        for row in rows
    ]


def list_endpoints(scope: Scope) -> list[Item]:
    subscriptions = sorted(list_subscriptions(scope.workspace), key=lambda s: s.created_at)
    with tenant_session_scope(scope.workspace) as session:
        return [
            {
                "id": sub.id,
                "url": _shown(sub.url),
                "created_at": sub.created_at,
                "deliveries": _deliveries(session, scope.workspace, sub.id),
            }
            for sub in subscriptions
        ]


def add(scope: Scope, url: str) -> tuple[Item, str]:
    """A new HTTPS endpoint and, once, its signing secret."""
    url = url.strip()
    parts = urlsplit(url)
    if len(url) > URL_MAX or parts.scheme != "https" or not parts.hostname:
        raise WebhookError
    if parts.username or parts.password:
        raise WebhookError
    if len(list_subscriptions(scope.workspace)) >= MAX_ENDPOINTS:
        raise WebhookLimitError
    try:
        sub, secret = subscribe(scope.workspace, url, caller=UserCaller(scope.actor))
    except InvalidWebhookUrlError:
        raise WebhookError from None
    except PermissionError:
        raise WebhooksUnavailableError from None
    except EncryptionError:
        raise WebhookKeyMissingError from None
    item = {"id": sub.id, "url": _shown(sub.url), "created_at": sub.created_at, "deliveries": []}
    return item, secret


def remove(scope: Scope, endpoint_id: uuid.UUID) -> None:
    """Remove an endpoint: no further deliveries to it. Repeatable."""
    try:
        unsubscribe(scope.workspace, endpoint_id, caller=UserCaller(scope.actor))
    except WebhookSubscriptionNotFoundError:
        raise RecordNotFoundError from None
    except PermissionError:
        raise WebhooksUnavailableError from None
