// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The receipts clip, 30 seconds, made along the rules of video-shotcraft:
 * the real screen fills the frame, each shot has one move, and what you must
 * read stands still. A title, the receipts into your own cloud folder, then
 * only real Huismus: Overzicht, Verwerken read line by line and filling in,
 * Klopt three times, faster each time, and "Niets meer te verwerken". Then
 * the screen falls away, only its sparrow is left, and that one flies off.
 *
 * Every screen is real: scripts/promo_film.py takes them from Huismus on
 * made-up data (public/opname/, with opname.json saying where things are).
 * The sentence always stands in the same band under the screen, never on it.
 * Everything is cut on the music: 120 bpm, so one beat is 15 frames.
 */
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Easing,
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

const b = (beats: number) => beats * 15;
export const DURATION = b(60);

const SCENE = {
  folder: b(5),
  overview: b(11),
  read: b(17),
  fill: b(25),
  check: b(33),
  done: b(42.25),
  strip: b(48),
  end: b(50.5),
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const at = (frame: number, input: number[], output: number[]) =>
  interpolate(frame, input, output, { easing: EASE, ...clamp });
const between = (frame: number, from: number, to: number, fade = 8) =>
  Math.min(at(frame, [from, from + fade], [0, 1]), at(frame, [to - fade, to], [1, 0]));
const opname = (file: string) => staticFile(`opname/${file}`);

const Mus: React.FC<{ size: number; flying?: boolean; frame?: number }> = ({ size, flying = false, frame = 0 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden style={{ overflow: "visible", display: "block" }}>
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
          transform: Math.floor(frame / 3) % 2 ? "scaleY(-0.75) rotate(10deg)" : "rotate(-6deg)",
        }}
      />
    ) : (
      <path d="M7.6 14.6c2.2-2.3 5.6-2.4 7.8-.2-2.3 2.1-5.5 2.2-7.8.2Z" fill={C.accent} />
    )}
    <circle cx="16.6" cy="7.9" r="1" fill={C.surface} />
  </svg>
);

// -- The sentence band ---------------------------------------------------------------

const BAND_TOP = 910;
const MID = BAND_TOP / 2;

const CAPTIONS: { from: number; to: number; plain: string; blue: string }[] = [
  { from: SCENE.folder, to: SCENE.overview, plain: "Foto in je ", blue: "eigen cloudmap." },
  { from: SCENE.overview, to: SCENE.read, plain: "Huismus ", blue: "haalt ze op." },
  { from: SCENE.read, to: SCENE.fill, plain: "Jouw eigen AI ", blue: "leest ze." },
  { from: SCENE.fill, to: SCENE.check, plain: "En vult de ", blue: "uitgave in." },
  { from: SCENE.check, to: SCENE.done, plain: "Jij zegt alleen: ", blue: "Klopt." },
  { from: SCENE.done, to: SCENE.strip, plain: "Drie bonnetjes. ", blue: "Klaar." },
];

const Band: React.FC<{ pill: string | null }> = ({ pill }) => {
  const frame = useCurrentFrame();
  const shown = between(frame, SCENE.folder - 6, SCENE.strip + 4, 8);
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: BAND_TOP,
        width: 1920,
        height: 1080 - BAND_TOP,
        background: C.surface,
        boxShadow: "0 -10px 30px rgba(60,45,30,.08)",
        opacity: shown,
      }}
    >
      {CAPTIONS.map((c) => {
        const opacity = between(frame, c.from, c.to, 7);
        const y = at(frame, [c.from, c.from + 12], [26, 0]);
        return (
          <div
            key={c.plain}
            style={{
              position: "absolute",
              left: 72,
              top: 38,
              fontSize: 80,
              lineHeight: 1.15,
              fontWeight: 800,
              letterSpacing: -2.5,
              color: C.text,
              whiteSpace: "nowrap",
              opacity,
              transform: `translateY(${y}px)`,
            }}
          >
            {c.plain}
            <span style={{ color: C.primary }}>{c.blue}</span>
          </div>
        );
      })}
      {pill && (
        <div
          style={{
            position: "absolute",
            right: 72,
            top: 42,
            padding: "14px 40px",
            borderRadius: 999,
            background: C.accentSoft,
            color: C.accentInk,
            fontSize: 62,
            fontWeight: 800,
            letterSpacing: -1,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {pill}
        </div>
      )}
    </div>
  );
};

// -- Shot 1: one sentence, pressed on the paper ---------------------------------------

const Stamp: React.FC<{ word: string; from: number; blue?: boolean }> = ({ word, from, blue }) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [from, from + 9], [0, 1], { easing: Easing.bezier(0.2, 0.75, 0.3, 1), ...clamp });
  return (
    <span
      style={{
        display: "inline-block",
        color: blue ? C.primary : C.text,
        opacity: t,
        filter: `blur(${(1 - t) * 7}px)`,
        transform: `scale(${1.28 - 0.28 * t})`,
      }}
    >
      {word}
    </span>
  );
};

const Opening: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame > SCENE.folder + 4) return null;
  const line = at(frame, [b(3), b(4)], [0, 1]);
  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        opacity: at(frame, [SCENE.folder - 6, SCENE.folder + 2], [1, 0]),
        fontSize: 172,
        fontWeight: 800,
        letterSpacing: -6,
        lineHeight: 1.08,
      }}
    >
      <div style={{ display: "flex", gap: 48 }}>
        <Stamp word="Bonnetjes" from={4} />
        <Stamp word="overtypen?" from={12} />
      </div>
      <div style={{ fontSize: 132, letterSpacing: -4, marginTop: 16 }}>
        <Stamp word="Hoeft niet meer." from={b(2.25)} blue />
      </div>
      <div
        style={{
          width: 300,
          height: 10,
          borderRadius: 5,
          marginTop: 40,
          background: C.accent,
          transform: `scaleX(${line})`,
        }}
      />
    </AbsoluteFill>
  );
};

// -- Shot 2: the receipts go into the cloud folder -------------------------------------

const PILE = [
  { x: 70, y: 200, r: -8, i: 0, land: SCENE.folder + 2 },
  { x: 370, y: 160, r: 2, i: 1, land: SCENE.folder + b(1) },
  { x: 670, y: 200, r: 9, i: 2, land: SCENE.folder + b(1.75) },
];
const FOLDER = { x: 1060, y: 290, w: 790, h: 350 };
const INTO = b(8.25);

const Folder: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (frame < SCENE.folder - 2 || frame > SCENE.overview + 4) return null;
  const pop = spring({ frame: frame - b(7.75), fps, config: { damping: 15 } });
  const leave = at(frame, [SCENE.overview - 6, SCENE.overview + 3], [0, 1]);
  const count = Math.min(3, Math.max(0, Math.floor((frame - INTO - 14) / 6) + 1));
  return (
    <AbsoluteFill style={{ opacity: 1 - leave }}>
      <div
        style={{
          position: "absolute",
          left: FOLDER.x,
          top: FOLDER.y,
          width: FOLDER.w,
          height: FOLDER.h,
          padding: "48px 60px",
          boxSizing: "border-box",
          background: C.surface,
          borderRadius: 32,
          boxShadow: SHADOW,
          opacity: pop,
          transform: `scale(${pop})`,
        }}
      >
        <svg width="110" height="110" viewBox="0 0 24 24" fill={C.primarySoft} stroke={C.primary} strokeWidth="1.5">
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
        </svg>
        <div style={{ fontSize: 66, fontWeight: 800, color: C.text, letterSpacing: -1.5, marginTop: 8 }}>
          Huismus bonnetjes
        </div>
        <div style={{ fontSize: 48, color: C.muted, marginTop: 6 }}>
          Dropbox · {count} {count === 1 ? "foto" : "foto's"}
        </div>
      </div>
      {PILE.map((p, n) => {
        const drop = spring({ frame: frame - p.land, fps, config: { damping: 14, stiffness: 170 } });
        // Each one faster than the one before, as cards are dealt.
        const start = INTO + [0, 12, 19][n];
        const go = at(frame, [start, start + 14], [0, 1]);
        if (go >= 1) return null;
        const x = interpolate(go, [0, 1], [p.x, FOLDER.x + 300]);
        const y = interpolate(go, [0, 1], [p.y, FOLDER.y + 120]) - Math.sin(go * Math.PI) * 90;
        return (
          <Img
            key={n}
            src={opname(data.receipts[p.i].file)}
            style={{
              position: "absolute",
              left: x,
              top: y - (1 - drop) * 1100,
              width: 760,
              transformOrigin: "0 0",
              transform: `scale(${interpolate(go, [0, 1], [0.44, 0.08])}) rotate(${p.r * (1 - go) + (1 - drop) * 30}deg)`,
              filter: "drop-shadow(0 18px 26px rgba(60,45,30,.22))",
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

// The sparrow of the first shots: lands on the folder, and leaves for the app.
const ROUTE = [
  { f: b(8.75), x: 1400, y: -240 },
  { f: b(10), x: 1640, y: 172 },
  { f: b(10.6), x: 1640, y: 172 },
  { f: b(11.6), x: 2150, y: -220 },
];
const VisitingBird: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < ROUTE[0].f || frame > ROUTE[3].f) return null;
  const f = ROUTE.map((s) => s.f);
  const flying = frame < ROUTE[1].f || frame > ROUTE[2].f;
  const peck = frame > b(10.05) && frame < b(10.55) && Math.floor(frame / 2.5) % 2 === 0 ? 16 : 3;
  return (
    <div
      style={{
        position: "absolute",
        left: at(frame, f, ROUTE.map((s) => s.x)),
        top: at(frame, f, ROUTE.map((s) => s.y)) + (flying ? Math.sin(frame / 2.2) * 7 : 0),
        transformOrigin: "50% 100%",
        transform: `rotate(${flying ? -10 : peck}deg)`,
        filter: "drop-shadow(0 8px 10px rgba(60,45,30,.18))",
      }}
    >
      <Mus size={130} flying={flying} frame={frame} />
    </div>
  );
};

// -- The camera over the real screens --------------------------------------------------

const W = data.viewport.width;
const H = data.viewport.height;
const CAM_EASE = Easing.bezier(0.33, 0, 0.15, 1);

type Key = { f: number; cx: number; cy: number; z: number; rx?: number; ry?: number };

const lens = (frame: number, keys: Key[]) => {
  const f = keys.map((k) => k.f);
  const get = (pick: (k: Key) => number) =>
    interpolate(frame, f, keys.map(pick), { easing: CAM_EASE, ...clamp });
  return { cx: get((k) => k.cx), cy: get((k) => k.cy), z: get((k) => k.z), rx: get((k) => k.rx ?? 0), ry: get((k) => k.ry ?? 0) };
};

const Screen: React.FC<{ keys: Key[]; opacity: number; children: React.ReactNode }> = ({ keys, opacity, children }) => {
  const frame = useCurrentFrame();
  const c = lens(frame, keys);
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        width: 1920,
        height: BAND_TOP,
        overflow: "hidden",
        perspective: 2200,
        perspectiveOrigin: `960px ${MID}px`,
        opacity,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: W,
          height: H,
          overflow: "hidden",
          borderRadius: 18,
          background: C.bg,
          boxShadow: SHADOW,
          transformOrigin: "0 0",
          transform: `translate(960px, ${MID}px) scale(${c.z}) rotateX(${c.rx}deg) rotateY(${c.ry}deg) translate(${-c.cx}px, ${-c.cy}px)`,
        }}
      >
        {children}
      </div>
    </div>
  );
};

const PageImage: React.FC<{ file: string }> = ({ file }) => (
  <Img src={opname(file)} style={{ position: "absolute", left: 0, top: 0, width: W, height: H }} />
);

/** Four corners that pull in on a target, like a camera finding focus. */
const Finder: React.FC<{ box: Box; from: number; to: number }> = ({ box, from, to }) => {
  const frame = useCurrentFrame();
  const [x, y, w, h] = box;
  const t = interpolate(frame, [from, from + 7], [0, 1], { easing: Easing.out(Easing.back(1.7)), ...clamp });
  if (frame < from || frame > to) return null;
  const arm = 16;
  const corner = (key: string, style: React.CSSProperties) => (
    <div key={key} style={{ position: "absolute", width: arm, height: arm, borderColor: C.accent, borderStyle: "solid", borderWidth: 0, ...style }} />
  );
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: w,
        height: h,
        transform: `scale(${1.75 - 0.75 * t})`,
        opacity: Math.min(1, at(frame, [from, from + 4], [0, 1]), at(frame, [to - 5, to], [1, 0])),
      }}
    >
      {corner("a", { left: 0, top: 0, borderLeftWidth: 4, borderTopWidth: 4 })}
      {corner("b", { right: 0, top: 0, borderRightWidth: 4, borderTopWidth: 4 })}
      {corner("c", { left: 0, bottom: 0, borderLeftWidth: 4, borderBottomWidth: 4 })}
      {corner("d", { right: 0, bottom: 0, borderRightWidth: 4, borderBottomWidth: 4 })}
    </div>
  );
};

// -- Shot 3: the real Overzicht --------------------------------------------------------

const OVERVIEW_KEYS: Key[] = [
  { f: SCENE.overview, cx: 720, cy: 520, z: 0.92, rx: 16, ry: -14 },
  { f: b(13), cx: 720, cy: 342, z: 1.333 },
  { f: b(14.75), cx: 844, cy: 260, z: 1.75 },
  { f: SCENE.read + 8, cx: 844, cy: 260, z: 1.75 },
];

const Overview: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < SCENE.overview - 2 || frame > SCENE.read + 8) return null;
  const opacity = Math.min(at(frame, [SCENE.overview - 2, SCENE.overview + 6], [0, 1]), at(frame, [SCENE.read, SCENE.read + 8], [1, 0]));
  return (
    <Screen keys={OVERVIEW_KEYS} opacity={opacity}>
      <PageImage file={data.overview.file} />
      <Finder box={[...data.overview.boxes.banner.slice(0, 2).map((v) => v - 6), data.overview.boxes.banner[2] + 12, data.overview.boxes.banner[3] + 12]} from={b(14.5)} to={SCENE.read + 8} />
    </Screen>
  );
};

// -- Shots 4 to 6: the real Verwerken ----------------------------------------------------

const items = data.items;
const first = items[0];
const photo = first.boxes.photo;
const total = first.receipt.totalAt;

const VALUES = [
  { key: "supplier", text: first.receipt.supplier, from: b(26.25), y: 0.17, also: ["date", "description", "line"] },
  { key: "amount", text: `€ ${first.receipt.total}`, from: b(28.25), y: total, also: ["category", "total"] },
  { key: "vat", text: `btw € ${first.receipt.vat}`, from: b(30.25), y: total + 0.075, also: [] as string[] },
] as const;
const FLIGHT = 16;

// The line moves evenly (a machine reading); a value is framed once it has passed.
const SCAN = { from: b(18.5), to: b(23.5), top: 0.08, end: 0.62 };
const scanAt = (y: number) => SCAN.from + ((y + 0.02 - SCAN.top) / (SCAN.end - SCAN.top)) * (SCAN.to - SCAN.from);
const valueBox = (y: number): Box => [photo[0] + photo[2] * 0.14, photo[1] + photo[3] * y - 22, photo[2] * 0.72, 44];

const KLOPT = [b(36), b(39.5), b(41.5)];
const SWIPE = 12;

const VERWERKEN_KEYS: Key[] = [
  { f: SCENE.read, cx: 800, cy: 433, z: 1.2 },
  { f: b(18.5), cx: 860, cy: 433, z: 1.655 },
  { f: b(27.4), cx: 860, cy: 433, z: 1.655 },
  { f: b(28.1), cx: 860, cy: 605, z: 1.655 },
  { f: SCENE.check, cx: 860, cy: 605, z: 1.655 },
  { f: b(34.5), cx: 960, cy: 880, z: 2 },
  { f: b(36.75), cx: 960, cy: 880, z: 2 },
  { f: b(38.25), cx: 720, cy: 730, z: 1.2 },
  { f: b(42), cx: 720, cy: 730, z: 1.2 },
  { f: b(43.25), cx: 830, cy: 262, z: 1.75 },
  { f: SCENE.end, cx: 830, cy: 262, z: 1.75 },
];

const toScreen = (frame: number, x: number, y: number) => {
  const c = lens(frame, VERWERKEN_KEYS);
  return { x: 960 + (x - c.cx) * c.z, y: MID + (y - c.cy) * c.z, z: c.z };
};

const coverBox = (key: keyof typeof first.boxes): Box => {
  const [x, y, w, h] = first.boxes[key];
  if (key === "total") return [x - 8, y - 5, w + 16, h + 10];
  if (key === "category") return [x, y, w - 40, h];
  return [x, y, w, h];
};

/** A field's real contents, hidden until the value lands, then wiped open. */
const FieldCover: React.FC<{ box: Box; from: number; seam?: boolean }> = ({ box, from, seam }) => {
  const frame = useCurrentFrame();
  const [x, y, w, h] = box;
  const wipe = at(frame, [from, from + 9], [0, 100]);
  return (
    <>
      <div style={{ position: "absolute", left: x + 2, top: y + 2, width: w - 4, height: h - 4, borderRadius: 7, background: C.surface, clipPath: `inset(0 0 0 ${wipe}%)` }} />
      {seam && (
        <div style={{ position: "absolute", left: x + 4, top: y + h - 2, width: w - 8, height: 4, borderRadius: 2, background: C.accent, opacity: between(frame, from, from + 26, 6) }} />
      )}
    </>
  );
};

const SwipedCard: React.FC<{ file: string; at: number }> = ({ file, at: when }) => {
  const frame = useCurrentFrame();
  const go = at(frame, [when + 3, when + 3 + SWIPE], [0, 1]);
  if (frame < when || go >= 1) return null;
  const x = first.boxes.head[0] - 8;
  const y = first.boxes.notice[1] - 8;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: W - x, height: H - y, overflow: "hidden", transform: `translateX(${go * 1300}px)`, background: C.bg }}>
      <Img src={opname(file)} style={{ position: "absolute", left: -x, top: -y, width: W, height: H }} />
    </div>
  );
};

const KloptPress: React.FC<{ box: Box; at: number }> = ({ box, at: when }) => {
  const frame = useCurrentFrame();
  const [x, y, w, h] = box;
  const t = frame - when;
  if (t > 10 || t < -b(1)) return null;
  const ripple = interpolate(t, [0, 10], [0, 1], clamp);
  return (
    <>
      <div style={{ position: "absolute", left: x - 7, top: y - 7, width: w + 14, height: h + 14, borderRadius: 13, border: `4px solid ${C.accent}`, opacity: between(frame, when - b(1), when + 3, 5) }} />
      {t >= 0 && (
        <div style={{ position: "absolute", left: x + w / 2 - 15 - 70 * ripple, top: y + h / 2 - 15 - 70 * ripple, width: 30 + 140 * ripple, height: 30 + 140 * ripple, borderRadius: "50%", border: `4px solid ${C.primary}`, opacity: 1 - ripple }} />
      )}
    </>
  );
};

// What falls away, outside in, each to its own side; the card goes last.
const [emptyX, emptyY, emptyW, emptyH] = data.done.boxes.empty;
const musBox = data.done.boxes.mus;
const TEXT_TOP = musBox[1] + musBox[3] + 14;
const LAYERS: { box: Box; dx: number; dy: number; delay: number; patch?: Box[] }[] = [
  { box: [0, 0, 280, H], dx: -200, dy: 0, delay: 0 },
  { box: [280, 0, W - 280, emptyY - 3], dx: 0, dy: -130, delay: 5 },
  {
    box: [emptyX - 3, emptyY - 3, emptyW + 6, emptyH + 6],
    dx: 0,
    dy: 60,
    delay: 15,
    patch: [[emptyX + 4, TEXT_TOP, emptyW - 8, emptyY + emptyH - TEXT_TOP - 4], musBox],
  },
  { box: [emptyX + 4, TEXT_TOP, emptyW - 8, emptyY + emptyH - TEXT_TOP - 4], dx: 0, dy: 110, delay: 10 },
];

const Slice: React.FC<(typeof LAYERS)[number]> = ({ box, dx, dy, delay, patch }) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [SCENE.strip + delay, SCENE.strip + delay + 14], [0, 1], { easing: Easing.in(Easing.quad), ...clamp });
  const [x, y, w, h] = box;
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, opacity: 1 - t, transform: `translate(${dx * t}px, ${dy * t}px)` }}>
      <div style={{ position: "absolute", left: x, top: y, width: w, height: h, overflow: "hidden", borderRadius: patch ? 12 : 0 }}>
        <Img src={opname(data.done.file)} style={{ position: "absolute", left: -x, top: -y, width: W, height: H }} />
        {patch?.map(([px, py, pw, ph]) => (
          <div key={py} style={{ position: "absolute", left: px - x, top: py - y, width: pw, height: ph, background: C.surface }} />
        ))}
      </div>
    </div>
  );
};

const Verwerken: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < SCENE.read - 2 || frame > SCENE.end) return null;
  const opacity = at(frame, [SCENE.read - 2, SCENE.read + 6], [0, 1]);
  const baseIndex = KLOPT.filter((when) => frame >= when).length;
  const base = baseIndex < items.length ? items[baseIndex].file : data.done.file;
  const scan = interpolate(frame, [SCAN.from, SCAN.to], [SCAN.top, SCAN.end], clamp);
  const notice = first.boxes.notice;
  const noticeShows = b(32);
  return (
    <Screen keys={VERWERKEN_KEYS} opacity={opacity}>
      {frame < SCENE.strip ? <PageImage file={base} /> : LAYERS.map((layer) => <Slice key={layer.delay} {...layer} />)}
      {frame < SCENE.strip && items.map((item, i) => <SwipedCard key={item.file} file={item.file} at={KLOPT[i]} />)}
      {frame < SCENE.check &&
        VALUES.flatMap((value) => {
          const from = value.from + FLIGHT - 2;
          return [
            <FieldCover key={value.key} box={coverBox(value.key)} from={from} seam />,
            ...value.also.map((key) => <FieldCover key={key} box={coverBox(key as keyof typeof first.boxes)} from={from} />),
          ];
        })}
      {frame < noticeShows + 12 && (
        <div style={{ position: "absolute", left: notice[0] - 2, top: notice[1] - 2, width: notice[2] + 4, height: notice[3] + 4, background: C.bg, opacity: at(frame, [noticeShows, noticeShows + 12], [1, 0]) }} />
      )}
      {frame < SCAN.to + 6 && (
        <div style={{ position: "absolute", left: photo[0], top: photo[1], width: photo[2], height: photo[3], overflow: "hidden", opacity: between(frame, SCAN.from - 3, SCAN.to + 6, 5) }}>
          <div style={{ position: "absolute", left: 0, top: photo[3] * scan - 70, width: photo[2], height: 70, background: `linear-gradient(to bottom, transparent, ${C.accent}55)`, borderBottom: `3px solid ${C.accent}` }} />
        </div>
      )}
      {VALUES.map((value) => (
        <Finder key={value.key} box={valueBox(value.y)} from={scanAt(value.y)} to={value.from + 6} />
      ))}
      {items.map((item, i) => (
        <KloptPress key={item.file} box={item.boxes.klopt} at={KLOPT[i]} />
      ))}
    </Screen>
  );
};

const ValueChip: React.FC<{ value: (typeof VALUES)[number] }> = ({ value }) => {
  const frame = useCurrentFrame();
  const from = value.from;
  if (frame < from - 6 || frame > from + FLIGHT + 3) return null;
  const field = first.boxes[value.key];
  const start = toScreen(frame, photo[0] + photo[2] / 2, photo[1] + photo[3] * value.y);
  const end = toScreen(frame, field[0] + field[2] * 0.5, field[1] + field[3] / 2);
  const lift = interpolate(frame, [from - 6, from], [0, 1], { easing: Easing.out(Easing.back(1.5)), ...clamp });
  const go = at(frame, [from + 2, from + FLIGHT], [0, 1]);
  return (
    <div
      style={{
        position: "absolute",
        left: interpolate(go, [0, 1], [start.x, end.x]),
        top: interpolate(go, [0, 1], [start.y, end.y]) - Math.sin(go * Math.PI) * 50,
        transform: `translate(-50%, -50%) scale(${lift * interpolate(go, [0, 1], [1, 0.72])})`,
        padding: "12px 34px",
        background: C.accent,
        color: C.text,
        fontSize: 70,
        fontWeight: 800,
        letterSpacing: -1.5,
        borderRadius: 18,
        whiteSpace: "nowrap",
        boxShadow: "0 16px 40px rgba(134,71,15,.35)",
        opacity: at(frame, [from + FLIGHT, from + FLIGHT + 3], [1, 0]),
      }}
    >
      {value.text}
    </div>
  );
};

// -- The end: the page falls away, its sparrow stays and flies off -----------------------

const PERCH = { x: 960, y: 210, size: 190 };
const FLY_OFF = b(56.5);

const SurvivingBird: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < SCENE.strip) return null;
  const from = toScreen(SCENE.strip, musBox[0] + musBox[2] / 2, musBox[1] + musBox[3] / 2);
  const move = at(frame, [SCENE.strip + 14, b(51.5)], [0, 1]);
  const away = interpolate(frame, [FLY_OFF, b(59)], [0, 1], { easing: Easing.in(Easing.quad), ...clamp });
  const startSize = musBox[3] * from.z;
  const x = interpolate(move, [0, 1], [from.x, PERCH.x]) + away * 1250;
  const y = interpolate(move, [0, 1], [from.y, PERCH.y]) - away * 560;
  const size = interpolate(move, [0, 1], [startSize, PERCH.size]) * (1 - 0.4 * away);
  const flying = (move > 0 && move < 1) || away > 0;
  const peck = [b(52.5), b(54.5)].some((when) => frame >= when && frame < when + 10 && Math.floor((frame - when) / 2.5) % 2 === 0) ? 16 : 3;
  return (
    <div
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size / 2 + (flying ? Math.sin(frame / 2.2) * 7 : 0),
        transformOrigin: "50% 100%",
        transform: `rotate(${flying ? -10 : peck}deg)`,
      }}
    >
      <Mus size={size} flying={flying} frame={frame} />
    </div>
  );
};

const EndCard: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < b(51)) return null;
  const rise = (from: number, dist = 30) => ({
    opacity: at(frame, [from, from + 9], [0, 1]),
    transform: `translateY(${at(frame, [from, from + 13], [dist, 0])}px)`,
  });
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: 320, flexDirection: "column" }}>
      <div style={{ fontSize: 200, fontWeight: 800, letterSpacing: -7, lineHeight: 1, color: C.text, ...rise(b(51)) }}>Huismus</div>
      <div style={{ fontSize: 68, fontWeight: 600, color: C.muted, marginTop: 20, letterSpacing: -1, ...rise(b(52)) }}>Facturen en bonnetjes voor zzp'ers</div>
      <div style={{ fontSize: 56, fontWeight: 700, color: C.text, marginTop: 44, letterSpacing: -1, ...rise(b(53)) }}>Op je eigen computer, met je eigen cloud en AI.</div>
      <div style={{ fontSize: 72, fontWeight: 800, color: C.primary, marginTop: 44, letterSpacing: -1, ...rise(b(54)) }}>huismus.arnekrijnsen.com</div>
    </AbsoluteFill>
  );
};

// -- Sound, on the same beats ------------------------------------------------------------

const Sfx: React.FC<{ file: string; at: number; volume: number }> = ({ file, at: when, volume }) => (
  <Sequence from={Math.round(when)} durationInFrames={20}>
    <Audio src={staticFile(file)} volume={volume} />
  </Sequence>
);

const SOUND_MARKS: [string, number, number][] = [
  ...PILE.map((p): [string, number, number] => ["geluiden/click_002.ogg", p.land + 8, 0.5]),
  ...VALUES.map((v): [string, number, number] => ["opname/pop.wav", v.from + FLIGHT - 2, 0.5]),
  ...VALUES.map((v): [string, number, number] => ["geluiden/click_004.ogg", scanAt(v.y), 0.35]),
  // Klopt: each softer than the last, so three don't sound like a machine gun.
  ...KLOPT.flatMap((when, i): [string, number, number][] => [
    ["geluiden/click_001.ogg", when, 0.75 - i * 0.12],
    ["opname/woesj.wav", when + 3, 0.5 - i * 0.08],
  ]),
  ["opname/woesj.wav", SCENE.strip + 4, 0.5],
  ["opname/woesj.wav", FLY_OFF, 0.45],
];

export const Bonnetjes: React.FC = () => {
  const frame = useCurrentFrame();
  const fired = VALUES.filter((v) => frame >= scanAt(v.y)).length;
  const pill =
    frame >= b(14.5) && frame < SCENE.read
      ? "3 nieuw"
      : frame >= SCAN.from && frame < SCENE.fill
      ? `Gelezen ${fired}/3`
      : frame >= SCENE.check && frame < SCENE.done
        ? `${Math.min(3, 1 + KLOPT.filter((when) => frame >= when).length)} van 3`
        : null;
  return (
    <AbsoluteFill style={{ fontFamily: FONT, background: C.bg }}>
      <Audio src={opname("muziek.wav")} volume={(f) => interpolate(f, [DURATION - 25, DURATION], [0.9, 0.2], clamp)} />
      <Opening />
      <Folder />
      <Overview />
      <Verwerken />
      {VALUES.map((value) => (
        <ValueChip key={value.key} value={value} />
      ))}
      <Band pill={pill} />
      <EndCard />
      <VisitingBird />
      <SurvivingBird />
      <AbsoluteFill style={{ background: C.bg, opacity: at(frame, [DURATION - 8, DURATION], [0, 1]) }} />
      {SOUND_MARKS.map(([file, when, volume]) => (
        <Sfx key={`${file}${when}`} file={file} at={when} volume={volume} />
      ))}
    </AbsoluteFill>
  );
};
