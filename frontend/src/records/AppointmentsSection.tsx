import { Plus } from "lucide-react";
import { useState } from "react";
import { Button as AriaButton } from "react-aria-components";

import { useUpcoming } from "../api/appointments";
import { useAccess, useMe, useMembers } from "../api/queries";
import { LoadError } from "../components/StateNotice";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { useT } from "../i18n/useT";
import { AppointmentDialog, hostColour, STATUS_LABEL, STATUS_TONE, TimeRange } from "./appointmentParts";
import { ownerOptions } from "./parts";

/*
 * The contact drawer's appointments (decision P5-A 1): the contact's
 * appointments that have not ended, soonest first, each opening on the
 * Calendar, and "New appointment" with the contact filled in. Who may book
 * follows `/access`.
 */

export function AppointmentsSection({
  workspaceId,
  contact,
  onOpen,
}: {
  workspaceId: string;
  contact: { id: string; name: string };
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const access = useAccess(workspaceId);
  const me = useMe();
  const meId = me.data?.user_id;
  const members = useMembers(workspaceId, 0, access.data?.actions.read_members === true);
  const list = useUpcoming(workspaceId, contact.id, 10);
  const [booking, setBooking] = useState(false);
  const items = list.data ?? [];
  const owners = ownerOptions(t, members.data?.items ?? [], meId);
  const hosts = owners.length ? owners : meId ? [{ id: meId, label: t("records.owner.me") }] : [];
  const canBook = access.data?.actions.create_appointment === true;
  return (
    <section className="drawer-section" aria-labelledby="contact-appointments-title">
      <h2 id="contact-appointments-title" className="drawer-section-title">
        {t("appointments.section", { count: items.length })}
      </h2>
      {list.isError ? <LoadError error={list.error} onRetry={() => void list.refetch()} /> : null}
      {items.length ? (
        <ul className="appointment-list">
          {items.map((a) => (
            <li key={a.id}>
              <AriaButton
                className="appointment-row"
                onPress={() => {
                  onOpen(a.id);
                }}
              >
                <span className="calendar-swatch tall" style={{ background: hostColour(a.host_user_id) }} aria-hidden="true" />
                <span className="appointment-row-text">
                  <span className="appointment-row-title">{a.title}</span>
                  <span className="appointment-row-meta">
                    <TimeRange start={a.starts_at} end={a.ends_at} />
                  </span>
                </span>
                <Badge tone={STATUS_TONE[a.status]}>{t(STATUS_LABEL[a.status])}</Badge>
              </AriaButton>
            </li>
          ))}
        </ul>
      ) : list.isPending ? null : (
        <p className="muted">{t("appointments.sectionEmpty")}</p>
      )}
      {canBook ? (
        <Button
          size="sm"
          onPress={() => {
            setBooking(true);
          }}
        >
          <Plus size={13} aria-hidden="true" />
          {t("appointments.new")}
        </Button>
      ) : null}
      {booking ? (
        <AppointmentDialog
          workspaceId={workspaceId}
          draft={{ start: nextHour(), contact: { id: contact.id, name: contact.name } }}
          hosts={hosts}
          meId={meId}
          onClose={() => {
            setBooking(false);
          }}
        />
      ) : null}
    </section>
  );
}

function nextHour(): Date {
  const start = new Date();
  start.setHours(start.getHours() + 1, 0, 0, 0);
  return start;
}
