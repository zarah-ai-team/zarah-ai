import React from "react";

const Svg = ({ size = 30, children, ...rest }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden="true"
    {...rest}
  >
    {children}
  </svg>
);

export const PlaneIcon = (props) => (
  <Svg {...props}>
    <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
  </Svg>
);

export const DocumentIcon = (props) => (
  <Svg {...props}>
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M6 2h7l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm7 1.5V8h4.5L13 3.5zM8 13h8v1.6H8V13zm0 3.4h8V18H8v-1.6zm0-6.8h5v1.6H8V9.6z"
    />
  </Svg>
);

export const ClockIcon = (props) => (
  <Svg {...props}>
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zm.85-15a.85.85 0 0 0-1.7 0v5.5c0 .47.38.85.85.85h4a.85.85 0 0 0 0-1.7h-3.15V7z"
    />
  </Svg>
);

export const BriefcaseIcon = (props) => (
  <Svg {...props}>
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M9 4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2h-6V4zm-2 2V4a3 3 0 0 1 3-3h4a3 3 0 0 1 3 3v2h3a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3z"
    />
  </Svg>
);

export const UsersIcon = (props) => (
  <Svg {...props}>
    <path d="M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zm7 .5a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 18.25C2 15.9 5.58 14 9 14s7 1.9 7 4.25V20H2v-1.75zm14.5-3.7c1.95.34 5.5 1.55 5.5 3.7V20h-4.5v-1.75c0-1.36-.4-2.5-1-3.4l-.01-.01c.01-.01.01-.01.01-.29z" />
  </Svg>
);

export const FolderCheckIcon = (props) => (
  <Svg {...props}>
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M2 6a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6zm14.3 6.55-4.5 4.5-2.6-2.6 1.1-1.1 1.5 1.5 3.4-3.4 1.1 1.1z"
    />
  </Svg>
);
