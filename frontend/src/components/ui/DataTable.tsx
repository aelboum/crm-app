import type { ReactNode } from "react";

export interface Column<Row> {
  key: string;
  header: string;
  render: (row: Row) => ReactNode;
  align?: "start" | "end";
  /** Hidden below 760 px; the first column is always shown. */
  hideNarrow?: boolean;
}

interface Props<Row> {
  caption: string;
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  empty: ReactNode;
}

/**
 * A semantic table in the design's style (36 px uppercase header, 48 px
 * rows). It scrolls horizontally inside its own box on narrow screens, so
 * the page never does.
 */
export function DataTable<Row>({ caption, columns, rows, rowKey, empty }: Props<Row>) {
  if (rows.length === 0) return <>{empty}</>;
  return (
    <div className="table-scroll">
      <table className="data-table">
        <caption className="caption">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={[c.align === "end" ? "end" : "", c.hideNarrow ? "hide-narrow" : ""]
                  .join(" ")
                  .trim()}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={[c.align === "end" ? "end" : "", c.hideNarrow ? "hide-narrow" : ""]
                    .join(" ")
                    .trim()}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
