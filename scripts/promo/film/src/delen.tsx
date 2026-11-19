// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What both films share: the timing helpers, the logo, and the marks drawn
 * over a real screen (a ring, a press, the app's toast). */
import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { C, EASE, huisstijl } from "./huismus";

export type Box = number[]; // x, y, width, height in CSS pixels of the screen
export type Cam = { f: number; x: number; y: number; s: number };

export const at = (frame: number, input: number[], output: number[]) =>
  interpolate(frame, input, output, {
    easing: EASE,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

export const fadeInOut = (frame: number, from: number, to: number, fade = 12) =>
  Math.min(at(frame, [from, from + fade], [0, 1]), at(frame, [to - fade, to], [1, 0]));

export const opname = (file: string) => staticFile(`opname/${file}`);
export const center = (b: Box) => ({ x: b[0] + b[2] / 2, y: b[1] + b[3] / 2 });

/** Where the camera is at `frame`: centre and scale, between its keys. */
export function camera(frame: number, keys: Cam[]) {
  const f = keys.map((k) => k.f);
  return {
    x: at(frame, f, keys.map((k) => k.x)),
    y: at(frame, f, keys.map((k) => k.y)),
    s: at(frame, f, keys.map((k) => k.s)),
  };
}

/** The logo "Tegel" with the word, as on the site (docs/design/icons/). */
export const Logo: React.FC<{ height: number; style?: React.CSSProperties }> = ({ height, style }) => (
  <Img src={huisstijl("logo.svg")} style={{ height, width: "auto", display: "block", ...style }} />
);

export const Tegel: React.FC<{ size: number }> = ({ size }) => (
  <Img src={huisstijl("tegel.svg")} style={{ width: size, height: size, display: "block" }} />
);

/** A petrol ring around a box on the screen, drawn in screen pixels. */
export const Ring: React.FC<{ box: Box; from: number; to: number; pad?: number; radius?: number }> = ({
  box,
  from,
  to,
  pad = 8,
  radius = 12,
}) => {
  const frame = useCurrentFrame();
  const opacity = fadeInOut(frame, from, to, 8);
  const grow = at(frame, [from, from + 14], [10, 0]);
  const [x, y, w, h] = box;
  return (
    <div
      style={{
        position: "absolute",
        left: x - pad - grow,
        top: y - pad - grow,
        width: w + 2 * (pad + grow),
        height: h + 2 * (pad + grow),
        borderRadius: radius + grow,
        border: `3px solid ${C.primary}`,
        boxShadow: "0 0 0 7px rgba(13, 107, 110, 0.2)",
        opacity,
      }}
    />
  );
};

/** A press on a button: a quick dip and a ripple, with the click. */
export const Press: React.FC<{ box: Box; at: number }> = ({ box, at: when }) => {
  const frame = useCurrentFrame();
  const [x, y, w, h] = box;
  const t = frame - when;
  if (t < -2 || t > 18) return null;
  const ripple = interpolate(t, [0, 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const dip = t >= 0 && t < 5 ? 0.28 : 0;
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: x,
          top: y,
          width: w,
          height: h,
          borderRadius: 10,
          background: `rgba(6, 32, 31, ${dip})`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: x + w / 2 - 60 * ripple - 20,
          top: y + h / 2 - 60 * ripple - 20,
          width: 40 + 120 * ripple,
          height: 40 + 120 * ripple,
          borderRadius: "50%",
          border: `3px solid ${C.text}`,
          opacity: (1 - ripple) * 0.7,
        }}
      />
    </>
  );
};

/** Huismus's toast, as the app shows it (huismus.css, .toast), in screen pixels. */
export const Toast: React.FC<{ text: string; from: number; to: number }> = ({ text, from, to }) => {
  const frame = useCurrentFrame();
  const opacity = fadeInOut(frame, from, to, 6);
  const y = at(frame, [from, from + 10], [-8, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: 1044,
        top: 16,
        width: 380,
        height: 58,
        boxSizing: "border-box",
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        padding: "12px 14px",
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 12,
        boxShadow: "0 2px 6px rgba(6,20,21,.08), 0 18px 48px rgba(6,20,21,.2)",
        fontSize: 15,
        fontWeight: 700,
        color: C.text,
        opacity,
        transform: `translateY(${y}px)`,
      }}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={C.primaryInk} strokeWidth="2">
        <circle cx="12" cy="12" r="9" />
        <path d="m8.5 12.5 2.4 2.3L15.5 10" />
      </svg>
      {text}
    </div>
  );
};

/** A petrol tick in a soft circle, for a short list of points. */
export const Check: React.FC<{ size: number }> = ({ size }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" style={{ flex: "none" }}>
    <circle cx="12" cy="12" r="11" fill={C.primarySoft} />
    <path d="m7 12.4 3.3 3.3L17 9" stroke={C.primary} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/** The film's background: the app's light, a little lighter where the eye goes. */
export const BACKGROUND = `radial-gradient(1500px 1000px at 72% 30%, #FFFFFF 0%, ${C.bg} 58%, ${C.surface3} 100%)`;
