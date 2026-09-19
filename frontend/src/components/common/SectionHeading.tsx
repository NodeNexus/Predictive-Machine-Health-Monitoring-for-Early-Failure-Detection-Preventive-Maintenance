import type { ReactNode } from "react";

interface Props {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function SectionHeading({ eyebrow, title, description, action, className = "" }: Props) {
  return (
    <div className={"section-heading " + className}>
      <div className="section-heading__copy">
        {eyebrow && <div className="section-heading__eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p className="section-heading__description">{description}</p>}
      </div>
      {action && <div className="section-heading__action">{action}</div>}
    </div>
  );
}
