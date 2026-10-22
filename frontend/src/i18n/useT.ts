import { useIntl } from "react-intl";

import type { MessageId } from "./en";

type Values = Record<string, string | number>;

/** Typed message lookup: an unknown id is a type error, not a blank string. */
export function useT() {
  const intl = useIntl();
  return (id: MessageId, values?: Values) => intl.formatMessage({ id }, values);
}
