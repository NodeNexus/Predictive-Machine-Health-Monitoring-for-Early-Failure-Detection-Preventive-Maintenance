import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
  tone?: "paper" | "ink" | "muted" | "amber";
  as?: "section" | "div";
}

export function Panel({ children, className = "", tone = "paper", as = "section" }: Props) {
  const Tag = as;
  return <Tag className={"panel panel-" + tone + " panel--" + tone + " " + className}>{children}</Tag>;
}
