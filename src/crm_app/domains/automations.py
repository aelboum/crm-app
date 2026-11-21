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

Triggers (decision P8-B adds all but the first): `contact_created`
(optional `sources`), `tag_added` (`tag_id`), `form_submitted` (optional
`form_id`), `appointment_booked` on a booking page (optional
`booking_page_id`) and `deal_stage_changed` into a stage (`stage_id`, the
deal's contact). Decision P8-C adds `campaign_sent`, when the provider
accepts a campaign's email to the contact (never delivery; a rehearsal sends
nothing, so it never fires), and `campaign_unsubscribed`, when the contact
uses a campaign's unsubscribe link; both take an optional `campaign_id`.
Each automation runs at most once per contact, whatever the trigger, so
automations that trigger one another always stop.

Actions: `add_tag` and `remove_tag` (`tag_id`), `assign_owner`
(`user_id`), `set_lifecycle_stage` (`stage`), `create_task` (`title`,
`priority`, `due_minutes` or null, `assignee`: `contact_owner`, `none` or a
member's id), `notify_member` (`recipient`: `contact_owner` or a member's
id, and a fixed `message` the definition's author writes; decision P8-N),
`assign_round_robin` (`user_ids`, 2 to 20 members; decision P8-R), `wait`
(`minutes`), `wait_for_business_hours` (no arguments; decision P8-W) and
`set_custom_field` (`field_key` of a contact custom field and a fixed
`value` the author writes; decision P8-F). A field's key and type never
change, so the key names it; whether the field is active and the value fits
its type is checked at activation and again at each run.
Contacts created by an import never start an automation.

Conditions read the contact's `source` or `lifecycle_stage` (`in`,
`not_in`), whether it has an `email` (`present`, `absent`), its `tag`s
(`has`, `has_not`), or (decision P8-G) one contact custom field:
`{"field": "custom_field", "key": ..., "op": "in" | "not_in", "values":
[...]}` or `"op": "present" | "absent"` without values. Values have the
shapes `set_custom_field` takes; text compares without regard to case. A
field archived since activation counts as having no value.

Decision P8-H adds the contact's deals: `{"field": "deal", "op": "has" |
"has_not", "values": ["open", "won", "lost"]}` asks whether the contact has
a deal with one of those outcomes, and `{"field": "deal_stage", "op": "has"
| "has_not", "values": [stage ids]}` whether it has an open deal in one of
those stages. The stages must exist at activation; a stage removed since
simply matches no deal.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from crm_app.domains import custom_fields as field_rules
from crm_app.domains.opportunities import OUTCOMES
from crm_app.domains.records import SOURCES, STAGES, InvalidValue, visible_text

TRIGGERS = (
    "contact_created",
    "tag_added",
    "form_submitted",
    "appointment_booked",
    "deal_stage_changed",
    "campaign_sent",
    "campaign_unsubscribed",
)
# The record a trigger may be limited to, and whether it must be.
TRIGGER_SUBJECTS: dict[str, tuple[str, bool]] = {
    "tag_added": ("tag_id", True),
    "form_submitted": ("form_id", False),
    "appointment_booked": ("booking_page_id", False),
    "deal_stage_changed": ("stage_id", True),
    "campaign_sent": ("campaign_id", False),
    "campaign_unsubscribed": ("campaign_id", False),
}
# An import can create thousands of contacts at once (P8-A 3).
TRIGGER_SOURCES = tuple(source for source in SOURCES if source != "import")
ACTIONS = (
    "add_tag",
    "remove_tag",
    "assign_owner",
    "set_lifecycle_stage",
    "create_task",
    "notify_member",
    "assign_round_robin",
    "wait",
    "wait_for_business_hours",
    "set_custom_field",
)
PRIORITIES = ("high", "medium", "low")
MAX_ACTIONS = 10
MAX_AUTOMATIONS = 20
NAME_MAX = 100
TASK_TITLE_MAX = 200
# The fixed text of a `notify_member` step (P8-N): written by whoever edits
# the automation, never filled in from the contact.
NOTICE_MAX = 200
# A round-robin step's members (P8-R): at least two, so it is a rotation.
ROTATION_MIN, ROTATION_MAX = 2, 20
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
    trigger: str = "contact_created"
    # The tag, form, booking page or stage the trigger is limited to.
    subject_id: str | None = None

    def branch(self, name: str) -> tuple[Action, ...]:
        return self.yes if name == "yes" else self.no

    def _trigger_json(self) -> dict[str, Any]:
        if self.trigger == "contact_created":
            return {"type": self.trigger, "sources": list(self.sources)}
        key, _ = TRIGGER_SUBJECTS[self.trigger]
        return {"type": self.trigger, key: self.subject_id}

    def as_json(self) -> dict[str, Any]:
        return {
            "trigger": self._trigger_json(),
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


def _notice(raw: Mapping[str, Any], where: str) -> Action:
    _keys(raw, {"type", "recipient", "message"}, where)
    message = " ".join(str(raw.get("message", "")).split())
    if not 1 <= len(message) <= NOTICE_MAX or not visible_text(message):
        raise InvalidValue(f"{where}.message: 1 to {NOTICE_MAX} visible characters")
    recipient = raw.get("recipient", "contact_owner")
    if recipient != "contact_owner":
        recipient = _uuid(recipient, f"{where}.recipient")
    return Action("notify_member", {"recipient": recipient, "message": message})


def _rotation(raw: Mapping[str, Any], where: str) -> Action:
    _keys(raw, {"type", "user_ids"}, where)
    given = raw.get("user_ids")
    if not isinstance(given, list):
        raise InvalidValue(f"{where}.user_ids: a list")
    users = list(dict.fromkeys(_uuid(u, f"{where}.user_ids") for u in given))
    if not ROTATION_MIN <= len(users) <= ROTATION_MAX:
        raise InvalidValue(f"{where}.user_ids: {ROTATION_MIN} to {ROTATION_MAX} members")
    return Action("assign_round_robin", {"user_ids": users})


def _field_key(given: object, where: str) -> str:
    try:
        return field_rules.key(given if isinstance(given, str) else "")
    except InvalidValue:
        raise InvalidValue(f"{where}: a custom field's key") from None


def _fixed_value(given: object, where: str) -> object:
    """A fixed value of a shape some field type accepts: true or false, a
    number, or trimmed visible text. Which field it must fit is checked at
    activation."""
    if isinstance(given, bool):
        return given
    if isinstance(given, int | float):
        try:
            return field_rules.value("number", None, given)
        except InvalidValue as exc:
            raise InvalidValue(f"{where}: {exc}") from None
    if isinstance(given, str):
        text = given.strip()
        if not 1 <= len(text) <= field_rules.TEXT_MAX or not visible_text(text):
            raise InvalidValue(f"{where}: 1 to {field_rules.TEXT_MAX} visible characters")
        return text
    raise InvalidValue(f"{where}: text, a number, or true or false")


def same_value(stored: object, wanted: object) -> bool:
    """Whether a stored custom field value equals a condition's value: of
    the same kind (true or false is never a number), text without regard
    to case."""
    if isinstance(stored, bool) or isinstance(wanted, bool):
        return isinstance(stored, bool) and isinstance(wanted, bool) and stored == wanted
    if isinstance(stored, str) and isinstance(wanted, str):
        return stored.casefold() == wanted.casefold()
    numbers = (int, float)
    return isinstance(stored, numbers) and isinstance(wanted, numbers) and stored == wanted


def _field_value(raw: Mapping[str, Any], where: str) -> Action:
    """`set_custom_field` (P8-F): a key and a fixed value of a shape some
    field type accepts; which field and type is checked at activation."""
    _keys(raw, {"type", "field_key", "value"}, where)
    key = _field_key(raw.get("field_key"), f"{where}.field_key")
    value = _fixed_value(raw.get("value"), f"{where}.value")
    return Action("set_custom_field", {"field_key": key, "value": value})


def _action(raw: object, where: str) -> Action:
    if not isinstance(raw, Mapping):
        raise InvalidValue(f"{where}: an object")
    kind = raw.get("type")
    if kind in ("add_tag", "remove_tag"):
        _keys(raw, {"type", "tag_id"}, where)
        return Action(kind, {"tag_id": _uuid(raw.get("tag_id"), f"{where}.tag_id")})
    if kind == "set_lifecycle_stage":
        _keys(raw, {"type", "stage"}, where)
        stage = raw.get("stage")
        if stage not in STAGES:
            raise InvalidValue(f"{where}.stage: one of {', '.join(STAGES)}")
        return Action(kind, {"stage": stage})
    if kind == "assign_owner":
        _keys(raw, {"type", "user_id"}, where)
        return Action(kind, {"user_id": _uuid(raw.get("user_id"), f"{where}.user_id")})
    if kind == "wait":
        _keys(raw, {"type", "minutes"}, where)
        minutes = _minutes(raw.get("minutes"), f"{where}.minutes", lowest=1)
        return Action(kind, {"minutes": minutes})
    if kind == "wait_for_business_hours":
        _keys(raw, {"type"}, where)
        return Action(kind, {})
    builder = {
        "create_task": _task,
        "notify_member": _notice,
        "assign_round_robin": _rotation,
        "set_custom_field": _field_value,
    }
    if isinstance(kind, str) and kind in builder:
        return builder[kind](raw, where)
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


def _field_condition(raw: Mapping[str, Any]) -> dict[str, Any]:
    """A condition on one contact custom field (P8-G)."""
    _keys(raw, {"field", "key", "op", "values"}, "condition")
    key = _field_key(raw.get("key"), "condition.key")
    op = raw.get("op")
    if op in ("present", "absent"):
        if "values" in raw:
            raise InvalidValue("condition.values: not with present or absent")
        return {"field": "custom_field", "key": key, "op": op}
    if op not in ("in", "not_in"):
        raise InvalidValue("condition.op: one of in, not_in, present, absent")
    given = raw.get("values")
    if not isinstance(given, list) or not 1 <= len(given) <= MAX_VALUES:
        raise InvalidValue(f"condition.values: 1 to {MAX_VALUES} values")
    values: list[object] = []
    for item in given:
        value = _fixed_value(item, "condition.values")
        if not any(same_value(value, seen) for seen in values):
            values.append(value)
    return {"field": "custom_field", "key": key, "op": op, "values": values}


def _condition(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise InvalidValue("condition: an object or null")
    if raw.get("field") == "custom_field":
        return _field_condition(raw)
    _keys(raw, {"field", "op", "values"}, "condition")
    field, op = raw.get("field"), raw.get("op")
    if field in ("source", "lifecycle_stage") and op in ("in", "not_in"):
        allowed = SOURCES if field == "source" else STAGES
        values = _values(raw.get("values"), allowed, "condition.values")
        return {"field": field, "op": op, "values": values}
    if field == "email" and op in ("present", "absent"):
        return {"field": field, "op": op}
    if field in ("tag", "deal_stage") and op in ("has", "has_not"):
        values = _values(raw.get("values"), None, "condition.values")
        return {"field": field, "op": op, "values": values}
    if field == "deal" and op in ("has", "has_not"):
        values = _values(raw.get("values"), OUTCOMES, "condition.values")
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
        raise InvalidValue(f"trigger.type: one of {', '.join(TRIGGERS)}")
    kind = str(trigger["type"])
    sources: tuple[str, ...] = ()
    subject: str | None = None
    if kind == "contact_created":
        _keys(trigger, {"type", "sources"}, "trigger")
        raw_sources = trigger.get("sources") or []
        if raw_sources:
            sources = tuple(_values(raw_sources, TRIGGER_SOURCES, "trigger.sources"))
    else:
        key, required = TRIGGER_SUBJECTS[kind]
        _keys(trigger, {"type", key}, "trigger")
        given = trigger.get(key)
        if given is None and required:
            raise InvalidValue(f"trigger.{key}: required")
        subject = None if given is None else _uuid(given, f"trigger.{key}")
    condition = _condition(raw.get("condition"))
    branches: dict[str, tuple[Action, ...]] = {}
    for branch in ("yes", "no"):
        steps = raw.get(branch) or []
        if not isinstance(steps, list) or len(steps) > MAX_ACTIONS:
            raise InvalidValue(f"{branch}: at most {MAX_ACTIONS} actions")
        branches[branch] = tuple(_action(step, f"{branch}[{i}]") for i, step in enumerate(steps))
    if condition is None and branches["no"]:
        raise InvalidValue("no: only with a condition")
    return Definition(sources, condition, branches["yes"], branches["no"], kind, subject)


def activatable(given: Definition) -> None:
    """The extra rule for activating: something to do."""
    if not given.yes and not given.no:
        raise InvalidValue("yes: at least one action")


def matches(given: Definition, trigger: str, subject_id: str | None) -> bool:
    """Whether an event (`trigger` about the tag, form, booking page or
    stage `subject_id`) starts the automation."""
    if given.trigger != trigger or trigger == "contact_created":
        return False
    return given.subject_id is None or given.subject_id == subject_id


def triggered_by(given: Definition, source: str) -> bool:
    """Whether a contact created with `source` starts the automation."""
    if given.trigger != "contact_created" or source not in TRIGGER_SOURCES:
        return False
    return not given.sources or source in given.sources


@dataclass(frozen=True)
class Facts:
    """What a condition may look at, read when the run starts."""

    source: str
    lifecycle_stage: str
    has_email: bool
    tag_ids: frozenset[str]
    # The value of the custom field a condition reads (P8-G); None when it
    # has none or the field is no longer active.
    custom_value: object = None
    # The outcomes of the contact's deals, and the stages of its open deals
    # (P8-H); read only for a condition on deals.
    deal_outcomes: frozenset[str] = frozenset()
    open_deal_stage_ids: frozenset[str] = frozenset()


def branch_for(condition: dict[str, Any] | None, facts: Facts) -> str:
    """`"yes"` or `"no"`; without a condition, always `"yes"`."""
    if condition is None:
        return "yes"
    field, op, values = condition["field"], condition["op"], condition.get("values", [])
    if field == "custom_field":
        present = facts.custom_value is not None
        if op in ("present", "absent"):
            matched = present == (op == "present")
        else:
            held = present and any(same_value(facts.custom_value, v) for v in values)
            matched = held if op == "in" else not held
    elif field == "email":
        matched = facts.has_email == (op == "present")
    elif field in ("tag", "deal", "deal_stage"):
        held_set = {
            "tag": facts.tag_ids,
            "deal": facts.deal_outcomes,
            "deal_stage": facts.open_deal_stage_ids,
        }[field]
        held = bool(held_set & set(values))
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
    if given.trigger == "tag_added" and given.subject_id:
        tags.add(given.subject_id)
    for step in (*given.yes, *given.no):
        if step.type in ("add_tag", "remove_tag"):
            tags.add(step.args["tag_id"])
        elif step.type == "assign_owner":
            users.add(step.args["user_id"])
        elif step.type == "create_task" and step.args["assignee"] not in ("contact_owner", "none"):
            users.add(step.args["assignee"])
        elif step.type == "notify_member" and step.args["recipient"] != "contact_owner":
            users.add(step.args["recipient"])
        elif step.type == "assign_round_robin":
            users.update(step.args["user_ids"])
    return tags, users


def condition_field(given: Definition) -> tuple[str, list[object]] | None:
    """The custom field key a condition reads and the values it compares
    with (P8-G), to check before activation; None for other conditions."""
    if not given.condition or given.condition["field"] != "custom_field":
        return None
    return given.condition["key"], list(given.condition.get("values", []))


def condition_stages(given: Definition) -> set[str]:
    """The pipeline stage ids a `deal_stage` condition names (P8-H), to
    check before activation."""
    if not given.condition or given.condition["field"] != "deal_stage":
        return set()
    return set(given.condition["values"])


def field_values(given: Definition) -> list[tuple[str, object]]:
    """The custom field keys and values a definition sets (P8-F), to check
    against the workspace's active contact fields before activation."""
    return [
        (step.args["field_key"], step.args["value"])
        for step in (*given.yes, *given.no)
        if step.type == "set_custom_field"
    ]
