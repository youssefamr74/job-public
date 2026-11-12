import type { SVGProps } from 'react';

function Icon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    />
  );
}

export function SearchIcon() {
  return (
    <Icon>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5 14 14" />
    </Icon>
  );
}

export function BellIcon() {
  return (
    <Icon>
      <path d="M4 6.5a4 4 0 0 1 8 0v3l1.2 2H2.8L4 9.5z" />
      <path d="M6.5 13.5a1.5 1.5 0 0 0 3 0" />
    </Icon>
  );
}

export function SettingsIcon() {
  return (
    <Icon>
      <circle cx="8" cy="8" r="2" />
      <path d="M8 1.5v1.6M8 12.9v1.6M14.5 8h-1.6M3.1 8H1.5M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1M12.6 12.6l-1.1-1.1M4.5 4.5 3.4 3.4" />
    </Icon>
  );
}

export function ChevronDownIcon() {
  return (
    <Icon width="12" height="12">
      <path d="m4 6 4 4 4-4" />
    </Icon>
  );
}

export function CheckIcon() {
  return (
    <Icon width="14" height="14">
      <path d="m3 8.5 3.2 3L13 4.5" />
    </Icon>
  );
}

export function CloseIcon() {
  return (
    <Icon>
      <path d="m4 4 8 8M12 4l-8 8" />
    </Icon>
  );
}
