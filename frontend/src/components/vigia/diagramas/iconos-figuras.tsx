/**
 * Iconos de línea (cuadrícula de 24 x 24) de las figuras de la presentación,
 * copiados de la propuesta aprobada. Solo se dibuja el trazo; el color, el
 * grosor y el tamaño los pone `Ic` en `primitivas.tsx`.
 */

import type { ReactNode } from "react";

export type NombreIcono =
  | "alert"
  | "bell"
  | "box"
  | "chart"
  | "check"
  | "cpu"
  | "db"
  | "doc"
  | "eye"
  | "lock"
  | "pencil"
  | "plug"
  | "pulse"
  | "scale"
  | "search"
  | "shield"
  | "term"
  | "users";

export const ICONOS: Record<NombreIcono, ReactNode> = {
  alert: (
    <>
      <path d="M8 2h8l6 6v8l-6 6H8l-6-6V8z" />
      <path d="M12 8v5M12 16h.01" />
    </>
  ),
  bell: (
    <>
      <path d="M 6 16V11a6 6 0 0 1 12 0v5l2 2H4z" />
      <path d="M10 21h4" />
    </>
  ),
  box: (
    <>
      <path d="M 3 7l9-4 9 4v10l-9 4-9-4z" />
      <path d="M 3 7l9 4 9-4M12 11v10" />
    </>
  ),
  chart: (
    <>
      <path d="M 3 3v18h18" />
      <path d="M7 15l4-4 3 3 5-6" />
    </>
  ),
  check: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <path d="M8 12l3 3 5-6" />
    </>
  ),
  cpu: (
    <>
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <rect x="9" y="9" width="6" height="6" />
      <path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" />
    </>
  ),
  db: (
    <>
      <path d="M 4 6c0-2 16-2 16 0v12c0 2-16 2-16 0z" />
      <path d="M 4 6c0 2 16 2 16 0M 4 12c0 2 16 2 16 0" />
    </>
  ),
  doc: (
    <>
      <path d="M 6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4M9 12h6M9 16h6" />
    </>
  ),
  eye: (
    <>
      <path d="M 2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </>
  ),
  pencil: (
    <>
      <path d="M 4 20l1-5L16 4l4 4L9 19z" />
    </>
  ),
  plug: (
    <>
      <path d="M9 2v5M15 2v5M 6 7h12v4a6 6 0 0 1-12 0zM12 17v5" />
    </>
  ),
  pulse: (
    <>
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </>
  ),
  scale: (
    <>
      <path d="M12 3v18M 6 21h12M 5 7h14M 5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0z" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-5-5" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" />
    </>
  ),
  term: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M7 10l3 2-3 2M12 15h5" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M 2 20c0-3.5 3-5.5 7-5.5s7 2 7 5.5" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M17 14c3 0 5 1.5 5 4" />
    </>
  ),
};
