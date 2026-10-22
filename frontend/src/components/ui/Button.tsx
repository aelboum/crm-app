import { Button as AriaButton, type ButtonProps } from "react-aria-components";

export type Variant = "primary" | "secondary" | "ghost" | "destructive";
export type Size = "sm" | "md" | "lg";

/** Class names for the design's button styles, also used on links styled as buttons. */
export function buttonClass(variant: Variant = "secondary", size: Size = "md"): string {
  return `btn btn-${variant} btn-${size}`;
}

interface Props extends ButtonProps {
  variant?: Variant;
  size?: Size;
}

/** The design's button (primary, secondary, ghost, destructive; 28/32/34 px). */
export function Button({ variant = "secondary", size = "md", className, ...props }: Props) {
  const extra = typeof className === "string" ? ` ${className}` : "";
  return <AriaButton {...props} className={buttonClass(variant, size) + extra} />;
}
