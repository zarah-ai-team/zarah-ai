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

export const TotalItinerariesIcon = (props) => (
  <Svg {...props}>
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M5 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h14a3 3 0 0 0 3-3V6a3 3 0 0 0-3-3H5zm2.2 5.4h9.6V10H7.2V8.4zm0 3.6h9.6v1.6H7.2V12zm0 3.6h6.4v1.6H7.2v-1.6z"
    />
  </Svg>
);

export const SavedIcon = (props) => (
  <Svg {...props}>
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M5 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h14a3 3 0 0 0 3-3V6a3 3 0 0 0-3-3H5zm2.2 7h9.6v1.6H7.2V10zm0 3.6h6.4v1.6H7.2v-1.6z"
    />
  </Svg>
);

export const InProgressIcon = (props) => (
  <Svg {...props}>
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M5 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h14a3 3 0 0 0 3-3V6a3 3 0 0 0-3-3H5zm2.2 7.2h6.4v1.6H7.2v-1.6zm9.55-2.85a1 1 0 0 1 1.4 0l1.05 1.05a1 1 0 0 1 0 1.4l-.7.7-2.45-2.45.7-.7zm-1.4 1.4 2.45 2.45-5.7 5.7H10v-2.4l5.35-5.75z"
    />
  </Svg>
);

export const CompletedIcon = (props) => (
  <Svg {...props}>
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M5 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h14a3 3 0 0 0 3-3V6a3 3 0 0 0-3-3H5zm12.5 6.4-6.5 6.5-3.5-3.5 1.4-1.4 2.1 2.1 5.1-5.1 1.4 1.4z"
    />
  </Svg>
);

export const ChatPlusIcon = ({ size = 24, ...rest }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    {...rest}
  >
    <path d="M14 4.5h-3.5A6.5 6.5 0 0 0 4 11v.5c0 1.18.31 2.29.86 3.25L4 18.5l3.85-.92A6.47 6.47 0 0 0 10.5 18H14" />
    <path d="M19 4v5M16.5 6.5h5" />
    <path d="M8.5 11h0.5M11.5 11h0.5" />
  </svg>
);
