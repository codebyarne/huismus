// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
// Huismus's own look (huismus/core/static/core/huismus.css, light mode).
import { Easing } from "remotion";

export const C = {
  bg: "#FBF8F3",
  surface: "#FFFFFF",
  surface2: "#F4EFE7",
  surface3: "#EBE4D9",
  text: "#2A2520",
  muted: "#6B6258",
  primary: "#1B6AC9",
  primarySoft: "#E3EEFB",
  accent: "#F4A259",
  accentSoft: "#FDEBD8",
  accentInk: "#86470F",
};

export const FONT =
  'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, "Helvetica Neue", Arial, sans-serif';

// One curve for every move: quick start, long soft landing.
export const EASE = Easing.bezier(0.25, 0.1, 0.1, 1);
export const SHADOW = "0 30px 80px rgba(60, 45, 30, 0.18), 0 6px 18px rgba(60, 45, 30, 0.10)";
