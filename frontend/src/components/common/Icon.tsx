import type { SVGProps } from "react";

export type IconName =
  | "activity"
  | "arrow"
  | "bell"
  | "chevron"
  | "database"
  | "grid"
  | "machine"
  | "menu"
  | "play"
  | "pulse"
  | "radio"
  | "settings"
  | "shield"
  | "spark"
  | "stop"
  | "thermometer"
  | "wave";

interface Props extends SVGProps<SVGSVGElement> {
  name: IconName;
  size?: number;
}

const paths: Record<IconName, string> = {
  activity: "M3 12h4l2-8 4 16 2-8h6",
  arrow: "M5 12h13m-5-5 5 5-5 5",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4",
  chevron: "m6 9 6 6 6-6",
  database: "M4 6c0-2 4-3 8-3s8 1 8 3-4 3-8 3-8-1-8-3Zm0 0v6c0 2 4 3 8 3s8-1 8-3V6m-16 6v6c0 2 4 3 8 3s8-1 8-3v-6",
  grid: "M4 4h6v6H4zm10 0h6v6h-6zM4 14h6v6H4zm10 0h6v6h-6z",
  machine: "M4 6h16v12H4zM8 6V3m8 3V3M8 12h8m-8 4h4",
  menu: "M4 7h16M4 12h16M4 17h16",
  play: "m8 5 11 7-11 7V5Z",
  pulse: "M3 12h3l2-4 4 9 3-13 2 8h4",
  radio: "M4 8a12 12 0 0 1 16 0M7 11a8 8 0 0 1 10 0M10 14a4 4 0 0 1 4 0M12 18h.01",
  settings: "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm0-12v2m0 13v2m9-8h-2M5 12H3m15.36-6.36-1.42 1.42M7.06 16.94l-1.42 1.42m12.72 0-1.42-1.42M7.06 7.06 5.64 5.64",
  shield: "M12 3 20 6v5c0 5-3.4 8.5-8 10-4.6-1.5-8-5-8-10V6l8-3Zm-3 9 2 2 4-4",
  spark: "m12 3 1.6 6.4L20 11l-6.4 1.6L12 19l-1.6-6.4L4 11l6.4-1.6L12 3Z",
  stop: "M6 6h12v12H6z",
  thermometer: "M10 13.5V5a2 2 0 1 1 4 0v8.5a4 4 0 1 1-4 0ZM12 16v-5",
  wave: "M3 12c2-8 4 8 6 0s4-8 6 0 4 8 6 0",
};

export function Icon({ name, size = 18, strokeWidth = 1.7, ...props }: Props) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={strokeWidth}
      {...props}
    >
      <path d={paths[name]} />
    </svg>
  );
}
