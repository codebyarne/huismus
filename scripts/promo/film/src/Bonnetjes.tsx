// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The receipts clip: a day's receipts go to your own cloud folder, Huismus
 * reads them with your own AI, and you only check them in Verwerken.
 *
 * The screens are real: scripts/promo_film.py takes them from Huismus on
 * made-up data (public/opname/, with opname.json saying where things are on
 * them). This file only edits them: titles, moves and highlights, in
 * Huismus's own colours (huismus.ts).
 */
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import data from "../public/opname/opname.json";
import { C, EASE, FONT, SHADOW } from "./huismus";

type Box = number[]; // x, y, width, height in CSS pixels of the screen

// -- The timeline, in frames (30 a second) ------------------------------------
const T = {
  readStart: 90, // the receipts go into Huismus
  screenStart: 200, // the app window comes up, on the overview
  item: [285, 495, 575], // Verwerken, one receipt each
  done: 655, // Niets meer te verwerken
  end: 735, // the closing card
};
export const DURATION = 830;

const at = (frame: number, input: number[], output: number[]) =>
  interpolate(frame, input, output, {
    easing: EASE,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const fadeInOut = (frame: number, from: number, to: number, fade = 12) =>
  Math.min(at(frame, [from, from + fade], [0, 1]), at(frame, [to - fade, to], [1, 0]));

const opname = (file: string) => staticFile(`opname/${file}`);

// -- Small parts ---------------------------------------------------------------

/** The sparrow of the logo (huismus/templates/site/_mus.html): the folded
 * wing while it sits, the raised wing flapping while it flies. */
const Mus: React.FC<{ size: number; flying?: boolean; frame?: number }> = ({ size, flying = false, frame = 0 }) => {
  // site.css's mus-flap: 0.16 s a stroke, up and down.
  const up = Math.floor(frame / 5) % 2 === 1;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden style={{ overflow: "visible" }}>
      <path d="M4 17C4 11.5 8.5 9.3 13.6 10c4.6.7 6.4 5.2 3 8.4-3 2.7-9.6 2.8-12.6-1.4Z" fill={C.primary} />
      <path d="M4.2 17 1 21.4l6-1.8Z" fill={C.primary} />
      <circle cx="15.4" cy="8.6" r="4.4" fill={C.primary} />
      <path d="M19.4 7.6 22.6 8.8l-3.2 1.1Z" fill={C.accent} />
      {flying ? (
        <path
          d="M9 14.2C6.2 11.2 5 7.2 5.8 2.6c3.2 2.2 5.6 6 6.8 11.1Z"
          fill={C.accent}
          style={{
            transformOrigin: "10.8px 14px",
            transform: up ? "scaleY(-0.75) rotate(10deg)" : "rotate(-6deg)",
          }}
        />
      ) : (
        <path d="M7.6 14.6c2.2-2.3 5.6-2.4 7.8-.2-2.3 2.1-5.5 2.2-7.8.2Z" fill={C.accent} />
      )}
      <circle cx="16.6" cy="7.9" r="1" fill={C.surface} />
    </svg>
  );
};

const Brand: React.FC<{ opacity: number }> = ({ opacity }) => (
  <div style={{ position: "absolute", left: 96, top: 72, display: "flex", alignItems: "center", gap: 16, opacity }}>
    <Mus size={56} />
    <span style={{ fontSize: 40, fontWeight: 700, color: C.text, letterSpacing: -0.5 }}>Huismus</span>
  </div>
);

/** A big line of text on the left, as on a slide, rising in. */
const Title: React.FC<{ lines: string[]; from: number; to: number; top?: number }> = ({
  lines,
  from,
  to,
  top = 330,
}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: 96, top, width: 860 }}>
      {lines.map((line, i) => {
        const start = from + i * 8;
        const opacity = fadeInOut(frame, start, to);
        const y = at(frame, [start, start + 18], [28, 0]);
        return (
          <div
            key={line}
            style={{
              fontSize: 84,
              lineHeight: 1.08,
              fontWeight: 750,
              letterSpacing: -2,
              color: i === lines.length - 1 && lines.length > 1 ? C.primary : C.text,
              opacity,
              transform: `translateY(${y}px)`,
            }}
          >
            {line}
          </div>
        );
      })}
    </div>
  );
};

/** A caption card over the screen, bottom left: white, with the accent bar. */
const Caption: React.FC<{ text: string; from: number; to: number }> = ({ text, from, to }) => {
  const frame = useCurrentFrame();
  const opacity = fadeInOut(frame, from, to, 10);
  const y = at(frame, [from, from + 16], [24, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: 72,
        bottom: 64,
        padding: "22px 34px 22px 30px",
        background: C.surface,
        borderRadius: 20,
        boxShadow: SHADOW,
        borderLeft: `8px solid ${C.accent}`,
        fontSize: 46,
        fontWeight: 650,
        color: C.text,
        letterSpacing: -0.6,
        opacity,
        transform: `translateY(${y}px)`,
      }}
    >
      {text}
    </div>
  );
};

/** A soft orange ring around a box on the screen, drawn in screen pixels. */
const Ring: React.FC<{ box: Box; from: number; to: number; pad?: number; radius?: number }> = ({
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
        border: `4px solid ${C.accent}`,
        boxShadow: `0 0 0 8px ${C.accentSoft}`,
        opacity,
      }}
    />
  );
};

/** A press on a button: a quick dip and a ripple, with the click. */
const Press: React.FC<{ box: Box; at: number }> = ({ box, at: when }) => {
  const frame = useCurrentFrame();
  const [x, y, w, h] = box;
  const t = frame - when;
  if (t < -2 || t > 18) return null;
  const ripple = interpolate(t, [0, 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const dip = t >= 0 && t < 5 ? 0.18 : 0;
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: x,
          top: y,
          width: w,
          height: h,
          borderRadius: 8,
          background: `rgba(10, 30, 70, ${dip})`,
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
          border: `3px solid ${C.primary}`,
          opacity: (1 - ripple) * 0.7,
        }}
      />
    </>
  );
};

/** Huismus's toast, as the app shows it after Klopt. */
const Toast: React.FC<{ from: number; to: number }> = ({ from, to }) => {
  const frame = useCurrentFrame();
  const opacity = fadeInOut(frame, from, to, 6);
  const y = at(frame, [from, from + 10], [-12, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: 1044,
        top: 16,
        width: 380,
        height: 58,
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "0 18px",
        background: C.surface,
        border: `1px solid ${C.surface3}`,
        borderRadius: 12,
        boxShadow: "0 8px 24px rgba(60,45,30,.12)",
        fontSize: 17,
        fontWeight: 650,
        color: C.text,
        opacity,
        transform: `translateY(${y}px)`,
      }}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2E7D4F" strokeWidth="2">
        <circle cx="12" cy="12" r="9" />
        <path d="m8 12.5 2.6 2.5L16 9.5" />
      </svg>
      Uitgave nagekeken.
    </div>
  );
};

// -- Scene 1 and 2: the receipts, and Huismus reading them --------------------

const Receipts: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fan = [
    { x: 1110, y: 250, r: -9 },
    { x: 1330, y: 200, r: 3 },
    { x: 1540, y: 270, r: 11 },
  ];
  return (
    <>
      {data.receipts.map((receipt, i) => {
        const arrive = spring({ frame: frame - 10 - i * 9, fps, config: { damping: 16, mass: 0.8 } });
        // Into Huismus: each one shrinks into its row of the card (Reading).
        const go = at(frame, [T.readStart + i * 10, T.readStart + 24 + i * 10], [0, 1]);
        const row = { x: 1150, y: 330 + i * 150 };
        const x = interpolate(go, [0, 1], [fan[i].x, row.x - 40]);
        const y = interpolate(go, [0, 1], [fan[i].y, row.y - 60]);
        const scale = interpolate(go, [0, 1], [0.42, 0.11]);
        return (
          <Img
            key={receipt.file}
            src={opname(receipt.file)}
            style={{
              position: "absolute",
              left: x,
              top: y + (1 - arrive) * 900,
              width: 760,
              transformOrigin: "0 0",
              transform: `scale(${scale}) rotate(${fan[i].r * (1 - go)}deg)`,
              filter: "drop-shadow(0 30px 40px rgba(60,45,30,.22))",
              opacity: go > 0.98 ? 0 : 1,
            }}
          />
        );
      })}
    </>
  );
};

const ReadingCard: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = fadeInOut(frame, T.readStart, T.screenStart + 8, 14);
  const y = at(frame, [T.readStart, T.readStart + 20], [40, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: 1060,
        top: 230,
        width: 760,
        padding: "34px 40px",
        background: C.surface,
        borderRadius: 24,
        boxShadow: SHADOW,
        opacity,
        transform: `translateY(${y}px)`,
      }}
    >
      <div style={{ fontSize: 22, fontWeight: 650, color: C.muted, marginBottom: 18 }}>
        Dropbox › Huismus bonnetjes
      </div>
      {data.receipts.map((receipt, i) => {
        const done = frame >= T.readStart + 40 + i * 16;
        const rowIn = at(frame, [T.readStart + 12 + i * 10, T.readStart + 30 + i * 10], [0, 1]);
        return (
          <div
            key={receipt.file}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 22,
              height: 150,
              borderTop: i ? `1px solid ${C.surface3}` : "none",
              opacity: rowIn,
            }}
          >
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: 16,
                background: done ? C.primarySoft : C.surface2,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {done ? (
                <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke={C.primary} strokeWidth="2.4">
                  <path d="m6 12.5 4 4L18 8" />
                </svg>
              ) : (
                <div
                  style={{
                    width: 30,
                    height: 30,
                    borderRadius: "50%",
                    border: `4px solid ${C.surface3}`,
                    borderTopColor: C.primary,
                    transform: `rotate(${frame * 14}deg)`,
                  }}
                />
              )}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 34, fontWeight: 700, color: C.text }}>
                {done ? receipt.supplier : "Huismus leest…"}
              </div>
              <div style={{ fontSize: 26, color: C.muted, marginTop: 4 }}>
                {done ? receipt.category : " "}
              </div>
            </div>
            <div style={{ fontSize: 36, fontWeight: 700, color: C.text, opacity: done ? 1 : 0 }}>
              € {receipt.total}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// -- Scene 3: the app itself ------------------------------------------------------

type Cam = { f: number; x: number; y: number; s: number };

const W = data.viewport.width;
const H = data.viewport.height;
const WHOLE = { x: W / 2, y: H / 2, s: 0.8 };
const center = (b: Box) => ({ x: b[0] + b[2] / 2, y: b[1] + b[3] / 2 });

function camera(frame: number, keys: Cam[]) {
  const f = keys.map((k) => k.f);
  return {
    x: at(frame, f, keys.map((k) => k.x)),
    y: at(frame, f, keys.map((k) => k.y)),
    s: at(frame, f, keys.map((k) => k.s)),
  };
}

const items = data.items;
const first = items[0];
const photo = first.boxes.photo;
const totalOnPhoto = { x: photo[0] + photo[2] / 2, y: photo[1] + first.receipt.totalAt * photo[3] };
const amount = center(first.boxes.amount);
const banner = center(data.overview.boxes.banner);
const [i1, i2, i3] = T.item;

const CAMERA: Cam[] = [
  { f: T.screenStart, ...WHOLE },
  { f: T.screenStart + 22, ...WHOLE },
  { f: T.screenStart + 50, x: banner.x, y: banner.y + 120, s: 1.3 },
  { f: i1 - 6, x: banner.x, y: banner.y + 120, s: 1.3 },
  { f: i1 + 16, ...WHOLE },
  { f: i1 + 40, ...WHOLE },
  { f: i1 + 72, x: totalOnPhoto.x, y: totalOnPhoto.y, s: 1.75 },
  { f: i1 + 110, x: totalOnPhoto.x, y: totalOnPhoto.y, s: 1.75 },
  { f: i1 + 146, x: amount.x - 60, y: amount.y - 30, s: 1.6 },
  { f: i1 + 180, x: amount.x - 60, y: amount.y - 30, s: 1.6 },
  { f: i1 + 200, ...WHOLE },
  { f: T.done, ...WHOLE },
  { f: T.done + 30, x: center(data.done.boxes.empty).x, y: center(data.done.boxes.empty).y + 60, s: 1.05 },
  { f: T.end, x: center(data.done.boxes.empty).x, y: center(data.done.boxes.empty).y + 60, s: 1.05 },
];

/** Which screenshot shows when; each new one fades in over the last. */
const SCREENS = [
  { f: T.screenStart, file: data.overview.file },
  ...items.map((item, i) => ({ f: T.item[i], file: item.file })),
  { f: T.done, file: data.done.file },
];
const KLOPT = [i2 - 14, i3 - 14, T.done - 14];

const AppWindow: React.FC = () => {
  const frame = useCurrentFrame();
  const cam = camera(frame, CAMERA);
  const rise = at(frame, [T.screenStart, T.screenStart + 26], [520, 0]);
  const leave = at(frame, [T.end, T.end + 20], [0, 1]);
  const opacity = Math.min(at(frame, [T.screenStart, T.screenStart + 14], [0, 1]), 1 - leave);
  const scale = cam.s * (1 - 0.12 * leave);
  return (
    <AbsoluteFill style={{ opacity }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: W,
          height: H,
          transformOrigin: "0 0",
          transform: `translate(960px, ${540 + rise}px) scale(${scale}) translate(${-cam.x}px, ${-cam.y}px)`,
          borderRadius: 18,
          overflow: "hidden",
          boxShadow: SHADOW,
          background: C.bg,
          outline: `1px solid ${C.surface3}`,
        }}
      >
        {SCREENS.map((screen, i) => {
          const next = SCREENS[i + 1];
          if (frame < screen.f - 1 || (next && frame > next.f + 10)) return null;
          const opacity = i === 0 ? 1 : at(frame, [screen.f, screen.f + 9], [0, 1]);
          return (
            <Img
              key={screen.file}
              src={opname(screen.file)}
              style={{ position: "absolute", left: 0, top: 0, width: W, height: H, opacity }}
            />
          );
        })}
        {/* On the overview: the notice, pressed. */}
        <Ring box={data.overview.boxes.banner} from={T.screenStart + 44} to={i1 - 2} radius={14} />
        <Press box={data.overview.boxes.banner} at={i1 - 12} />
        {/* The first receipt: the total on the photo, then in the field. */}
        <Sequence from={0} layout="none">
          <div
            style={{
              position: "absolute",
              left: photo[0] + photo[2] * 0.12,
              top: totalOnPhoto.y - 26,
              width: photo[2] * 0.76,
              height: 52,
              borderRadius: 10,
              background: C.accent,
              mixBlendMode: "multiply",
              opacity: 0.35 * fadeInOut(frame, i1 + 70, i1 + 150, 10),
            }}
          />
        </Sequence>
        <Ring box={first.boxes.amount} from={i1 + 140} to={i1 + 196} />
        <Ring box={first.boxes.vat} from={i1 + 150} to={i1 + 196} />
        {items.map((item, i) => (
          <React.Fragment key={item.file}>
            {i > 0 && <Ring box={item.boxes.counter} from={T.item[i] + 6} to={T.item[i] + 40} radius={16} pad={6} />}
            <Ring box={item.boxes.klopt} from={KLOPT[i] - 22} to={KLOPT[i] + 4} pad={6} radius={10} />
            <Press box={item.boxes.klopt} at={KLOPT[i]} />
            <Toast from={KLOPT[i] + 14} to={KLOPT[i] + 70} />
          </React.Fragment>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// -- Scene 4: the closing card -------------------------------------------------------

const EndCard: React.FC = () => {
  // Inside its Sequence: frame 0 is T.end.
  const frame = useCurrentFrame() + T.end;
  const { fps } = useVideoConfig();
  const pop = spring({ frame: frame - T.end - 10, fps, config: { damping: 12 } });
  const chips = ["Lokale desktop-app", "Jouw eigen cloudmap", "Jouw eigen AI"];
  // As on the site: it pecks, takes off, and flies away over the top right.
  const t = frame - T.end;
  const peck = t >= 34 && t < 46 ? (Math.floor((t - 34) / 3) % 2 === 0 ? 14 : 4) : 0;
  const crouch = t >= 52 && t < 56 ? 0.9 : 1;
  const flying = t >= 56;
  const fly = at(frame, [T.end + 56, T.end + 84], [0, 1]);
  const flyX = interpolate(fly, [0, 1], [0, 1150]);
  const flyY = interpolate(fly, [0, 0.15, 1], [0, -40, -760]);
  const flyR = interpolate(fly, [0, 0.15, 1], [0, -8, -16]);
  const flyS = interpolate(fly, [0, 1], [1, 0.7]);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
      <div
        style={{
          opacity: pop,
          transformOrigin: "50% 100%",
          transform: `translate(${flyX}px, ${flyY}px) rotate(${peck + flyR}deg) scale(${pop * flyS}, ${pop * flyS * crouch})`,
        }}
      >
        <Mus size={170} flying={flying} frame={t} />
      </div>
      <div
        style={{
          fontSize: 110,
          fontWeight: 800,
          letterSpacing: -3,
          color: C.text,
          marginTop: 8,
          opacity: at(frame, [T.end + 16, T.end + 30], [0, 1]),
        }}
      >
        Huismus
      </div>
      <div style={{ fontSize: 40, color: C.muted, marginTop: 6, opacity: at(frame, [T.end + 22, T.end + 36], [0, 1]) }}>
        Facturen en uitgaven voor zzp'ers
      </div>
      <div style={{ display: "flex", gap: 18, marginTop: 48 }}>
        {chips.map((chip, i) => {
          const t = at(frame, [T.end + 32 + i * 6, T.end + 46 + i * 6], [0, 1]);
          return (
            <div
              key={chip}
              style={{
                padding: "14px 26px",
                borderRadius: 999,
                background: C.primarySoft,
                color: C.primary,
                fontSize: 28,
                fontWeight: 650,
                opacity: t,
                transform: `translateY(${(1 - t) * 16}px)`,
              }}
            >
              {chip}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// -- The film ----------------------------------------------------------------------

export const Bonnetjes: React.FC = () => {
  const frame = useCurrentFrame();
  const brand = Math.min(at(frame, [0, 14], [0, 1]), at(frame, [T.screenStart - 10, T.screenStart + 6], [1, 0]));
  return (
    <AbsoluteFill
      style={{
        fontFamily: FONT,
        background: `radial-gradient(1400px 900px at 75% 30%, ${C.surface} 0%, ${C.bg} 55%, ${C.surface2} 100%)`,
      }}
    >
      <Brand opacity={brand} />
      <Title lines={["Weer een dag", "vol bonnetjes."]} from={6} to={T.readStart + 4} />
      <Title lines={["Huismus leest ze,", "met jouw eigen AI."]} from={T.readStart + 8} to={T.screenStart + 4} />
      <Sequence from={0} durationInFrames={T.screenStart + 10}>
        <Receipts />
        <ReadingCard />
      </Sequence>
      <Caption text="Foto in je eigen cloudmap. Meer niet." from={36} to={T.readStart + 2} />
      <AppWindow />
      <Caption text="Jij kijkt alleen nog na." from={T.screenStart + 30} to={i1 + 30} />
      <Caption text="Het bedrag van de bon staat er al." from={i1 + 76} to={i1 + 196} />
      <Caption text="Klopt? Door naar de volgende." from={i1 + 200} to={T.done} />
      <Caption text="Drie bonnetjes. Klaar." from={T.done + 14} to={T.end + 4} />
      <Sequence from={T.end}>
        <EndCard />
      </Sequence>
      {[i1 - 12, ...KLOPT].map((when) => (
        <Sequence key={when} from={when} durationInFrames={20}>
          <Audio src={staticFile("geluiden/click_001.ogg")} volume={0.6} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
