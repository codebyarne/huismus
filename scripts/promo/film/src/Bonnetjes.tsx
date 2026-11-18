// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The receipts clip: a day's receipts go to your own cloud folder, Huismus
 * reads them with your own AI, and you only check them in Verwerken.
 *
 * The screens are real: scripts/promo_film.py takes them from Huismus on
 * made-up data (public/opname/, with opname.json saying where things are on
 * them). This file only edits them: titles, moves and highlights, in
 * Huismus's own look (huismus.ts: "Helder" in dark, the logo "Tegel").
 */
import React from "react";
import { AbsoluteFill, Audio, Img, interpolate, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import data from "../public/opname/opname.json";
import { at, BACKGROUND, Cam, camera, center, fadeInOut, Logo, opname, Press, Ring, Tegel, Toast } from "./delen";
import { C, DISPLAY, FONT, SHADOW } from "./huismus";

// -- The timeline, in frames (30 a second) ------------------------------------
const T = {
  readStart: 90, // the receipts go into Huismus
  screenStart: 200, // the app window comes up, on the overview
  item: [285, 495, 575], // Verwerken, one receipt each
  done: 655, // Niets meer te verwerken
  end: 735, // the closing card
};
export const DURATION = 870;

// -- Small parts ---------------------------------------------------------------

/** A big line of text on the left, as on a slide, rising in. */
const Title: React.FC<{ lines: string[]; from: number; to: number; top?: number }> = ({
  lines,
  from,
  to,
  top = 330,
}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: 96, top, width: 900 }}>
      {lines.map((line, i) => {
        const start = from + i * 8;
        const opacity = fadeInOut(frame, start, to);
        const y = at(frame, [start, start + 18], [28, 0]);
        return (
          <div
            key={line}
            style={{
              fontFamily: DISPLAY,
              fontSize: 88,
              lineHeight: 1.06,
              fontWeight: 700,
              letterSpacing: -1.6,
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

/** A caption card over the screen, bottom left, with a mint bar. */
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
        background: C.surface2,
        border: `1px solid ${C.borderStrong}`,
        borderRadius: 20,
        boxShadow: SHADOW,
        borderLeft: `8px solid ${C.primary}`,
        fontSize: 44,
        fontWeight: 600,
        color: C.text,
        letterSpacing: -0.8,
        opacity,
        transform: `translateY(${y}px)`,
      }}
    >
      {text}
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
        // Into Huismus: each one shrinks into its row of the card (ReadingCard).
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
              filter: "drop-shadow(0 30px 40px rgba(0,0,0,.5))",
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
        boxSizing: "border-box",
        padding: "34px 40px",
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 24,
        boxShadow: SHADOW,
        opacity,
        transform: `translateY(${y}px)`,
      }}
    >
      <div style={{ fontSize: 22, fontWeight: 600, color: C.muted, marginBottom: 18 }}>
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
              borderTop: i ? `1px solid ${C.border}` : "none",
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
                flex: "none",
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
              <div style={{ fontSize: 32, fontWeight: 650, color: C.text, letterSpacing: -0.4 }}>
                {done ? receipt.supplier : "Huismus leest…"}
              </div>
              <div style={{ fontSize: 25, color: C.muted, marginTop: 4 }}>{done ? receipt.category : " "}</div>
            </div>
            <div
              style={{
                fontFamily: DISPLAY,
                fontSize: 38,
                fontWeight: 700,
                letterSpacing: -1,
                color: C.text,
                opacity: done ? 1 : 0,
              }}
            >
              € {receipt.total}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// -- Scene 3: the app itself ------------------------------------------------------

const W = data.viewport.width;
const H = data.viewport.height;
const WHOLE = { x: W / 2, y: H / 2, s: 0.84 };

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
          outline: `1px solid ${C.border}`,
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
        <div
          style={{
            position: "absolute",
            left: photo[0] + photo[2] * 0.2,
            top: totalOnPhoto.y - 26,
            width: photo[2] * 0.64,
            height: 52,
            borderRadius: 10,
            background: C.primary,
            mixBlendMode: "multiply",
            opacity: 0.55 * fadeInOut(frame, i1 + 70, i1 + 150, 10),
          }}
        />
        <Ring box={first.boxes.amount} from={i1 + 140} to={i1 + 196} />
        <Ring box={first.boxes.vat} from={i1 + 150} to={i1 + 196} />
        {items.map((item, i) => (
          <React.Fragment key={item.file}>
            {i > 0 && <Ring box={item.boxes.counter} from={T.item[i] + 6} to={T.item[i] + 40} radius={16} pad={6} />}
            <Ring box={item.boxes.klopt} from={KLOPT[i] - 22} to={KLOPT[i] + 4} pad={6} radius={12} />
            <Press box={item.boxes.klopt} at={KLOPT[i]} />
            {/* The last Klopt's toast is on the real screen (klaar.png). */}
            {i < items.length - 1 && <Toast text="Uitgave nagekeken." from={KLOPT[i] + 14} to={KLOPT[i] + 70} />}
          </React.Fragment>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// -- Scene 4: the closing card -------------------------------------------------------

const EndCard: React.FC = () => {
  // Inside its Sequence: frame 0 is T.end.
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: frame - 10, fps, config: { damping: 14 } });
  const chips = ["Op je eigen computer", "Je eigen cloudmap", "Een AI-dienst die jij kiest"];
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
      <div style={{ opacity: Math.min(pop, 1), transform: `scale(${0.6 + 0.4 * pop})` }}>
        <Tegel size={168} />
      </div>
      <div
        style={{
          fontFamily: DISPLAY,
          fontSize: 116,
          fontWeight: 700,
          letterSpacing: -2.2,
          color: C.text,
          marginTop: 22,
          opacity: at(frame, [16, 30], [0, 1]),
        }}
      >
        Huismus
      </div>
      <div style={{ fontSize: 40, color: C.muted, marginTop: 2, opacity: at(frame, [22, 36], [0, 1]) }}>
        Je boekhouding op je eigen computer
      </div>
      <div style={{ display: "flex", gap: 18, marginTop: 44 }}>
        {chips.map((chip, i) => {
          const t = at(frame, [32 + i * 6, 46 + i * 6], [0, 1]);
          return (
            <div
              key={chip}
              style={{
                padding: "14px 26px",
                borderRadius: 999,
                background: C.primarySoft,
                color: C.primaryInk,
                fontSize: 28,
                fontWeight: 600,
                opacity: t,
                transform: `translateY(${(1 - t) * 16}px)`,
              }}
            >
              {chip}
            </div>
          );
        })}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 28,
          marginTop: 48,
          opacity: at(frame, [52, 66], [0, 1]),
        }}
      >
        <span style={{ fontSize: 34, color: C.muted }}>Gratis voor Mac en Windows</span>
        <span
          style={{
            padding: "14px 36px",
            borderRadius: 999,
            background: C.primary,
            color: C.onPrimary,
            fontFamily: DISPLAY,
            fontSize: 44,
            fontWeight: 700,
            letterSpacing: -0.6,
          }}
        >
          mijnhuismus.nl
        </span>
      </div>
    </AbsoluteFill>
  );
};

// -- The film ----------------------------------------------------------------------

export const Bonnetjes: React.FC = () => {
  const frame = useCurrentFrame();
  const brand = Math.min(at(frame, [0, 14], [0, 1]), at(frame, [T.screenStart - 10, T.screenStart + 6], [1, 0]));
  return (
    <AbsoluteFill style={{ fontFamily: FONT, background: BACKGROUND }}>
      <Logo height={64} style={{ position: "absolute", left: 96, top: 72, opacity: brand }} />
      <Title lines={["Weer een dag", "vol bonnetjes."]} from={6} to={T.readStart + 4} />
      <Title lines={["Huismus leest ze,", "met een AI die jij kiest."]} from={T.readStart + 8} to={T.screenStart + 4} />
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
