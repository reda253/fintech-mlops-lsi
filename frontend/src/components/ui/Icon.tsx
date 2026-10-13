import type { ReactNode, SVGProps } from 'react';

/** Jeu d'icônes trait 1.6 (viewBox 24), reproduisant le style filaire des maquettes. */
const PATHS = {
  dashboard: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.6" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.6" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.6" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.6" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.3" />
      <path d="M2.8 20c0-3.5 2.8-6 6.200-6s6.200 2.500 6.200 6" />
      <circle cx="17.200" cy="9" r="2.500" />
      <path d="M17.500 14.200c2.200.4 3.700 2.400 3.700 5" />
    </>
  ),
  transactions: <path d="M4 8h16M16 4l4 4-4 4M20 16H4M8 12l-4 4 4 4" />,
  chart: <path d="M3 20h18M6 20v-5M10 20V9M14 20v-8M18 20V5" />,
  sparkle: <path d="M12 3.200l2 5.800 5.800 2-5.800 2-2 5.800-2-5.800-5.800-2 5.800-2z" />,
  list: <path d="M4 7h16M4 12h16M4 17h10" />,
  bell: <path d="M6 16.500V11a6 6 0 1 1 12 0v5.500l1.500 2h-15zM10 21h4" />,
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4.500 21c0-4.100 3.400-7.500 7.500-7.500s7.500 3.400 7.500 7.500" />
    </>
  ),
  logout: <path d="M9 4H5.500A1.500 1.500 0 0 0 4 5.500v13A1.500 1.500 0 0 0 5.500 20H9M16 8l4 4-4 4M20 12H9" />,
  lock: (
    <>
      <rect x="4.500" y="10.500" width="15" height="10" rx="2.200" />
      <path d="M8 10.500V8a4 4 0 0 1 8 0v2.500" />
    </>
  ),
  file: <path d="M7 3h7l5 5v12.500a.5.5 0 0 1-.5.5h-11a.5.5 0 0 1-.5-.5v-17a.5.5 0 0 1 .5-.5zM14 3v5h5M9 13h6M9 17h6" />,
  activity: <path d="M3 12h4l3-7.500 4 15 3-7.500h4" />,
  trend: <path d="M3.500 17.500l5.500-6 4 3.500 7-8.500M15 6.500h5v5" />,
  search: (
    <>
      <circle cx="11" cy="11" r="6.800" />
      <path d="M20 20l-4.200-4.200" />
    </>
  ),
  panel: (
    <>
      <rect x="3.500" y="4" width="17" height="16" rx="3.200" />
      <path d="M10 4v16" />
    </>
  ),
  eye: (
    <>
      <path d="M2.500 12S6 5.800 12 5.800 21.500 12 21.500 12 18 18.200 12 18.200 2.500 12 2.500 12z" />
      <circle cx="12" cy="12" r="2.800" />
    </>
  ),
  eyeOff: (
    <>
      <path d="M2.500 12S6 5.800 12 5.800 21.500 12 21.500 12 18 18.200 12 18.200 2.500 12 2.500 12z" />
      <circle cx="12" cy="12" r="2.800" />
      <path d="M4 4l16 16" />
    </>
  ),
  check: <path d="M5 12.500l4.500 4.500L19 7.500" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  send: <path d="M21 3L3 10.500l7 3 3 7zM10 13.500L21 3" />,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  external: <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />,
  alert: (
    <>
      <path d="M12 3.500l9.500 16.500h-19z" />
      <path d="M12 10v4.500M12 17.200v.1" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name'> {
  name: IconName;
  size?: number;
}

/** Icône décorative par défaut (aria-hidden) ; fournir `aria-label` pour une icône porteuse de sens. */
export function Icon({ name, size = 20, strokeWidth = 1.6, ...rest }: IconProps) {
  const labelled = rest['aria-label'] !== undefined;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={labelled ? undefined : true}
      role={labelled ? 'img' : undefined}
      focusable="false"
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}
