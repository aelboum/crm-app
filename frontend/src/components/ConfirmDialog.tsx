import { useT } from "../i18n/useT";
import { Button } from "./ui/Button";
import { Dialog } from "./ui/Dialog";

interface Props {
  isOpen: boolean;
  message: string;
  /** Defaults to the generic "Confirm change" / "Confirm"; deletions name what they do. */
  title?: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** A blocking confirmation for Owner changes and removals. Focus is trapped and restored by React Aria. */
export function ConfirmDialog({ isOpen, message, title, confirmLabel, onConfirm, onCancel }: Props) {
  const t = useT();
  return (
    <Dialog
      isOpen={isOpen}
      title={title ?? t("confirm.title")}
      onClose={onCancel}
      role="alertdialog"
      actions={
        <>
          <Button onPress={onCancel}>{t("confirm.cancel")}</Button>
          <Button variant="destructive" onPress={onConfirm}>
            {confirmLabel ?? t("confirm.submit")}
          </Button>
        </>
      }
    >
      <p>{message}</p>
    </Dialog>
  );
}
