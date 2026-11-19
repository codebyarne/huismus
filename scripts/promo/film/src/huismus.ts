// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
// Huismus's own look, "Helder" in light (huismus/core/static/core/huismus.css):
// the films are light, as the site is (owner, 2026-11-19).
import { continueRender, delayRender, Easing, staticFile } from "remotion";

export const C = {
  bg: "#F1F5F4",
  surface: "#FFFFFF",
  surface2: "#F4F7F6",
  surface3: "#E6EEED",
  border: "#E1E8E7",
  borderStrong: "#C3D0CF",
  text: "#0C2325",
  muted: "#5E7274",
  primary: "#0D6B6E", // petrol
  onPrimary: "#FFFFFF",
  primarySoft: "#E6F4F3",
  primaryInk: "#0A5A5D",
  mint: "#5FC9C4", // petrol's light sister: a marker over a photo
  hero: "#0B4F51",
  heroMuted: "#B5E4E1",
  paper: "#FFFFFF",
  // The site's second colour (docs/design/ronde-8/README.md): at most once a screen.
  framboos: "#B4184F",
};

export const FONT = '"Inter", ui-sans-serif, system-ui, sans-serif';
export const DISPLAY = `"Bricolage Grotesque", ${FONT}`;

// One curve for every move: quick start, long soft landing.
export const EASE = Easing.bezier(0.25, 0.1, 0.1, 1);
export const SHADOW = "0 30px 80px rgba(12, 35, 37, 0.18), 0 6px 18px rgba(12, 35, 37, 0.08)";

/** What scripts/promo-film.sh copies into public/huisstijl/: the app's own
 * letters and the logo "Tegel", so the films never have a copy of their own. */
export const huisstijl = (file: string) => staticFile(`huisstijl/${file}`);

// The app's letters, loaded before the first frame is drawn.
const FACES: [string, string, string][] = [
  ["Inter", "100 900", "inter-latin-wght-normal.woff2"],
  ["Bricolage Grotesque", "200 800", "bricolage-grotesque-latin-opsz-normal.woff2"],
];
if (typeof document !== "undefined") {
  const waiting = delayRender("De letters van Huismus laden");
  Promise.all(
    FACES.map(([family, weight, file]) =>
      new FontFace(family, `url(${huisstijl(file)}) format("woff2")`, { weight }).load().then((face) => {
        document.fonts.add(face);
      }),
    ),
  ).then(() => continueRender(waiting));
}
