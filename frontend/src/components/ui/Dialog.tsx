import type { ReactNode } from "react";
import { Dialog as AriaDialog, Heading, Modal, ModalOverlay } from "react-aria-components";

interface Props {
  isOpen: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  actions: ReactNode;
  /** `alertdialog` for confirmations that interrupt; `dialog` for forms. */
  role?: "dialog" | "alertdialog";
}

/**
 * The design's dialog: 12 px radius, floating shadow, scrim. React Aria traps
 * focus inside, closes on Escape and returns focus to the trigger.
 */
export function Dialog({ isOpen, title, onClose, children, actions, role = "dialog" }: Props) {
  return (
    <ModalOverlay
      className="modal-overlay"
      isOpen={isOpen}
      isDismissable
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Modal className="modal">
        <AriaDialog className="dialog" role={role}>
          <Heading slot="title" className="dialog-title">
            {title}
          </Heading>
          <div className="dialog-body">{children}</div>
          <div className="dialog-actions">{actions}</div>
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}
