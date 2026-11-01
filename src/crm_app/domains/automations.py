"""Automation definitions (decision P8-A): pure rules, no database.

A definition is plain data, never code: one trigger, an optional condition
that picks a branch, and two branches of at most `MAX_ACTIONS` actions,
each one of a fixed set with checked arguments. Nothing in it is evaluated
as an expression; a condition compares a contact's stored value with
listed values.

    {
      "trigger": {"type": "contact_created", "sources": ["form", "booking"]},
      "condition": {"field": "source", "op": "in", "values": ["form"]} | null,
      "yes": [action, ...],
      "no": [action, ...]        # only with a condition
    }

Actions: `add_tag` (`tag_id`), `assign_owner` (`user_id`), `create_task`
(`title`, `priority`, `due_minutes` or null, `assignee`: `contact_owner`,
`none` or a member's id) and `wait` (`minutes`). Contacts created by an
import never start an automation.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from crm_app.domains.records import SOURCES, STAGES, InvalidValue, visible_text

TRIGGERS = ("contact_created",)
# An import can create thousands of contacts at once (P8-A 3).
TRIGGER_SOURCES = tuple(source for source in SOURCES if source != "import")
ACTIONS = ("add_tag", "assign_owner", "create_task", "wait")
PRIORITIES = ("high", "medium", "low")
MAX_ACTIONS = 10
MAX_AUTOMATIONS = 20
NAME_MAX = 100
TASK_TITLE_MAX = 200
MINUTES_MAX = 30 * 24 * 60
MAX_VALUES = 20


@dataclass(frozen=True)
class Action:
    type: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Definition:
    sources: tuple[str, ...]
    condition: dict[str, Any] | None
    yes: tuple[Action, ...]
    no: tuple[Action, ...]

    def branch(self, name: str) -> tuple[Action, ...]:
        return self.yes if name == "yes" else self.no

    def as_json(self) -> dict[str, Any]:
        return {
            "trigger": {"type": "contact_created", "sources": list(self.sources)},
            "condition": self.condition,
            "yes": [{"type": a.type, **a.args} for a in self.yes],
            "no": [{"type": a.type, **a.args} for a in self.no],
        }


def name(value: str) -> str:
    text = " ".join(value.split())
    if not 1 <= len(text) <= NAME_MAX or not visible_text(text):
        raise InvalidValue(f"name: 1 to {NAME_MAX} visible characters")
    return text


def _uuid(value: object, where: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise InvalidValue(f"{where}: not an id") from None


def _minutes(value: object, where: str, *, lowest: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lowest <= value <= MINUTES_MAX:
        raise InvalidValue(f"{where}: whole minutes from {lowest} to {MINUTES_MAX}")
    return value


def _keys(given: Mapping[str, Any], allowed: set[str], where: str) -> None:
    extra = set(given) - allowed
    if extra:
        raise InvalidValue(f"{where}: unknown field {sorted(extra)[0]}")


def _task(raw: Mapping[str, Any], where: str) -> Action:
    _keys(raw, {"type", "title", "priority", "due_minutes", "assignee"}, where)
    title = " ".join(str(raw.get("title", "")).split())
    if not 1 <= len(title) <= TASK_TITLE_MAX or not visible_text(title):
        raise InvalidValue(f"{where}.title: 1 to {TASK_TITLE_MAX} visible characters")
    priority = raw.get("priority", "medium")
    if priority not in PRIORITIES:
        raise InvalidValue(f"{where}.priority: one of {', '.join(PRIORITIES)}")
    due = raw.get("due_minutes")
    due = None if due is None else _minutes(due, f"{where}.due_minutes", lowest=0)
    assignee = raw.get("assignee", "contact_owner")
    if assignee not in ("contact_owner", "none"):
        assignee = _uuid(assignee, f"{where}.assignee")
    args = {"title": title, "priority": priority, "due_minutes": due, "assignee": assignee}
    return Action("create_task", args)


def _action(raw: object, where: str) -> Action:
    if not isinstance(raw, Mapping):
        raise InvalidValue(f"{where}: an object")
    kind = raw.get("type")
    if kind == "add_tag":
        _keys(raw, {"type", "tag_id"}, where)
        return Action(kind, {"tag_id": _uuid(raw.get("tag_id"), f"{where}.tag_id")})
    if kind == "assign_owner":
        _keys(raw, {"type", "user_id"}, where)
        return Action(kind, {"user_id": _uuid(raw.get("user_id"), f"{where}.user_id")})
    if kind == "wait":
        _keys(raw, {"type", "minutes"}, where)
        minutes = _minutes(raw.get("minutes"), f"{where}.minutes", lowest=1)
        return Action(kind, {"minutes": minutes})
    if kind == "create_task":
        return _task(raw, where)
    raise InvalidValue(f"{where}.type: one of {', '.join(ACTIONS)}")


def _values(raw: object, allowed: Sequence[str] | None, where: str) -> list[str]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_VALUES:
        raise InvalidValue(f"{where}: 1 to {MAX_VALUES} values")
    values: list[str] = []
    for item in raw:
        text = str(item) if allowed is not None else _uuid(item, where)
        if allowed is not None and text not in allowed:
            raise InvalidValue(f"{where}: one of {', '.join(allowed)}")
        if text not in values:
            values.append(text)
    return values


def _condition(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise InvalidValue("condition: an object or null")
    _keys(raw, {"field", "op", "values"}, "condition")
    field, op = raw.get("field"), raw.get("op")
    if field in ("source", "lifecycle_stage") and op in ("in", "not_in"):
        allowed = SOURCES if field == "source" else STAGES
        values = _values(raw.get("values"), allowed, "condition.values")
        return {"field": field, "op": op, "values": values}
    if field == "email" and op in ("present", "absent"):
        return {"field": field, "op": op}
    if field == "tag" and op in ("has", "has_not"):
        values = _values(raw.get("values"), None, "condition.values")
        return {"field": field, "op": op, "values": values}
    raise InvalidValue("condition: an unsupported field or operator")


def definition(raw: object) -> Definition:
    """A definition as stored, or `InvalidValue` naming the first rule it
    breaks. A draft may have empty branches; `activatable` asks for more."""
    if not isinstance(raw, Mapping):
        raise InvalidValue("definition: an object")
    _keys(raw, {"trigger", "condition", "yes", "no"}, "definition")
    trigger = raw.get("trigger")
    if not isinstance(trigger, Mapping) or trigger.get("type") not in TRIGGERS:
        raise InvalidValue("trigger.type: contact_created")
    _keys(trigger, {"type", "sources"}, "trigger")
    raw_sources = trigger.get("sources") or []
    sources = tuple(_values(raw_sources, TRIGGER_SOURCES, "trigger.sources")) if raw_sources else ()
    condition = _condition(raw.get("condition"))
    branches: dict[str, tuple[Action, ...]] = {}
    for branch in ("yes", "no"):
        steps = raw.get(branch) or []
        if not isinstance(steps, list) or len(steps) > MAX_ACTIONS:
            raise InvalidValue(f"{branch}: at most {MAX_ACTIONS} actions")
        branches[branch] = tuple(_action(step, f"{branch}[{i}]") for i, step in enumerate(steps))
    if condition is None and branches["no"]:
        raise InvalidValue("no: only with a condition")
    return Definition(sources, condition, branches["yes"], branches["no"])


def activatable(given: Definition) -> None:
    """The extra rule for activating: something to do."""
    if not given.yes and not given.no:
        raise InvalidValue("yes: at least one action")


def triggered_by(given: Definition, source: str) -> bool:
    """Whether a contact created with `source` starts the automation."""
    if source not in TRIGGER_SOURCES:
        return False
    return not given.sources or source in given.sources


@dataclass(frozen=True)
class Facts:
    """What a condition may look at, read when the run starts."""

    source: str
    lifecycle_stage: str
    has_email: bool
    tag_ids: frozenset[str]


def branch_for(condition: dict[str, Any] | None, facts: Facts) -> str:
    """`"yes"` or `"no"`; without a condition, always `"yes"`."""
    if condition is None:
        return "yes"
    field, op, values = condition["field"], condition["op"], condition.get("values", [])
    if field == "email":
        matched = facts.has_email == (op == "present")
    elif field == "tag":
        held = bool(facts.tag_ids & set(values))
        matched = held if op == "has" else not held
    else:
        value = facts.source if field == "source" else facts.lifecycle_stage
        matched = (value in values) == (op == "in")
    return "yes" if matched else "no"


def referenced(given: Definition) -> tuple[set[str], set[str]]:
    """The tag ids and member ids a definition names, to check before
    activation."""
    tags: set[str] = set()
    users: set[str] = set()
    if given.condition and given.condition["field"] == "tag":
        tags.update(given.condition["values"])
    for step in (*given.yes, *given.no):
        if step.type == "add_tag":
            tags.add(step.args["tag_id"])
        elif step.type == "assign_owner":
            users.add(step.args["user_id"])
        elif step.type == "create_task" and step.args["assignee"] not in ("contact_owner", "none"):
            users.add(step.args["assignee"])
    return tags, users
