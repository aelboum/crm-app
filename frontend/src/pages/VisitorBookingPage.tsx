import { CalendarCheck } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../api/client";
import { useCancelVisitorBooking, useVisitorBooking } from "../api/bookingPages";
import { Loading } from "../components/StateNotice";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import type { MessageId } from "../i18n/en";
import { useT } from "../i18n/useT";
import { KIND_LABEL, TimeRange } from "../records/appointmentParts";

/*
 * The visitor's own booking (decision P5-C 7): /app/b/<workspace>/manage#<token>.
 * The token stays in the fragment, which browsers never send, and goes to
 * the public routes in a request body. It shows the booking and cancels it
 * until it starts; nothing here needs a session.
 */

function failure(error: unknown): MessageId {
  if (error instanceof ApiError) {
    if (error.status === 404 || error.status === 422) return "visitorBooking.gone";
    if (error.code === "booking_not_cancellable") return "visitorBooking.started";
    if (error.status === 429) return "publicForm.error.busy";
    if (error.status === 503) return "publicForm.error.unavailable";
  }
  return "visitorBooking.failed";
}

export function VisitorBookingPage({ workspaceId, token }: { workspaceId: string; token: string }) {
  const t = useT();
  const booking = useVisitorBooking(workspaceId, token);
  const cancel = useCancelVisitorBooking(workspaceId, token);
  const [confirming, setConfirming] = useState(false);

  let body;
  if (token === "") {
    body = (
      <p className="notice error" role="alert">
        {t("visitorBooking.noToken")}
      </p>
    );
  } else if (booking.isPending) {
    body = <Loading />;
  } else if (booking.isError) {
    body = (
      <p className="notice error" role="alert">
        {t(failure(booking.error))}
      </p>
    );
  } else {
    const view = booking.data;
    body = (
      <div className="visitor-booking">
        <CalendarCheck size={26} aria-hidden="true" className="visitor-booking-icon" />
        <h1 className="public-form-title">{view.page_name ?? t("visitorBooking.title")}</h1>
        <p>
          <TimeRange start={view.starts_at} end={view.ends_at} />
        </p>
        <p className="muted">{t(KIND_LABEL[view.kind])}</p>
        {view.location ? (
          <p className="booking-location">{t("publicBooking.location", { location: view.location })}</p>
        ) : null}
        {view.cancelled ? (
          <p className="notice" role="status">
            {t(view.cancelled_by_visitor ? "visitorBooking.cancelledByYou" : "visitorBooking.cancelled")}
          </p>
        ) : view.can_cancel ? (
          <button
            type="button"
            className="btn btn-destructive btn-lg"
            disabled={cancel.isPending}
            onClick={() => {
              setConfirming(true);
            }}
          >
            {cancel.isPending ? t("visitorBooking.cancelling") : t("visitorBooking.cancel")}
          </button>
        ) : (
          <p className="muted">{t("visitorBooking.started")}</p>
        )}
        {cancel.isError ? (
          <p className="notice error" role="alert">
            {t(failure(cancel.error))}
          </p>
        ) : null}
        <Dialog
          isOpen={confirming}
          title={t("visitorBooking.cancelTitle")}
          role="alertdialog"
          onClose={() => {
            setConfirming(false);
          }}
          actions={
            <>
              <Button
                onPress={() => {
                  setConfirming(false);
                }}
              >
                {t("visitorBooking.keep")}
              </Button>
              <Button
                variant="destructive"
                onPress={() => {
                  setConfirming(false);
                  cancel.mutate();
                }}
              >
                {t("visitorBooking.cancel")}
              </Button>
            </>
          }
        >
          <p>{t("visitorBooking.cancelBody")}</p>
        </Dialog>
      </div>
    );
  }
  return (
    <main id="main" className="public-form-page">
      <div className="public-form-card booking-card">{body}</div>
      <p className="public-form-foot">{t("publicBooking.footer")}</p>
    </main>
  );
}
