import { Button, Dialog, Heading, Modal, ModalOverlay } from "react-aria-components";

import { useT } from "../i18n/useT";

interface Props {
  isOpen: boolean;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** A blocking confirmation for Owner changes and removals. Focus is trapped and restored by React Aria. */
export function ConfirmDialog({ isOpen, message, onConfirm, onCancel }: Props) {
  const t = useT();
  return (
    <ModalOverlay
      className="modal-overlay"
      isOpen={isOpen}
      isDismissable
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
    >
      <Modal className="modal">
        <Dialog className="dialog" role="alertdialog">
          <Heading slot="title">{t("confirm.title")}</Heading>
          <p>{message}</p>
          <div className="row">
            <Button className="button" onPress={onCancel}>
              {t("confirm.cancel")}
            </Button>
            <Button className="button danger" onPress={onConfirm}>
              {t("confirm.submit")}
            </Button>
          </div>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
