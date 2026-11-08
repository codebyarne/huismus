// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The receipts clip, 20 seconds. A pile of receipts, a sparrow, your own
 * cloud folder; then the real Verwerken screen, its fields filling in from
 * the receipt; then Klopt, Klopt, Klopt, and the sparrow flies off.
 *
 * Every screen is real: scripts/promo_film.py takes them from Huismus on
 * made-up data (public/opname/, with opname.json saying where things are).
 * Fields "fill in" by uncovering the real pixels. A sentence stands beside
 * the screen, never on it, and big chips carry the values for a phone.
 * Everything is cut on the music: 120 bpm, so one beat is 15 frames. Copy is
 * sized for a phone: at 390 px wide a 1920 px film shows at a fifth.
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

const BEAT = 15;
const b = (beats: number) => beats * BEAT;

const SCENE = {
  folder: b(6), // the receipts go to the cloud folder
  read: b(11), // the app comes up and Huismus reads
  check: b(21), // Klopt, Klopt, Klopt
  done: b(28), // Niets meer te verwerken
  end: b(31), // the closing card
};
export const DURATION = b(40);

const at = (frame: number, input: number[], output: number[]) =>
  interpolate(frame, input, output, {
    easing: EASE,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
const between = (frame: number, from: number, to: number, fade = 10) =>
  Math.min(at(frame, [from, from + fade], [0, 1]), at(frame, [to - fade, to], [1, 0]));
const opname = (file: string) => staticFile(`opname/${file}`);

// -- The sparrow ------------------------------------------------------------------

/** The sparrow of the logo (huismus/templates/site/_mus.html): the folded
 * wing while it sits, the raised wing flapping while it flies. */
const Mus: React.FC<{ size: number; flying?: boolean; frame?: number }> = ({
  size,
  flying = false,
  frame = 0,
}) => (
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
          // site.css's mus-flap: about 0.16 s a stroke.
          transform: Math.floor(frame / 3) % 2 ? "scaleY(-0.75) rotate(10deg)" : "rotate(-6deg)",
        }}
      />
    ) : (
      <path d="M7.6 14.6c2.2-2.3 5.6-2.4 7.8-.2-2.3 2.1-5.5 2.2-7.8.2Z" fill={C.accent} />
    )}
    <circle cx="16.6" cy="7.9" r="1" fill={C.surface} />
  </svg>
);

// The sparrow's whole route, in film pixels, from one scene to the next.
type Stop = { f: number; x: number; y: number; flying: boolean; size: number };
const PERCH_END = { x: 900, y: 298 };
const ROUTE: Stop[] = [
  { f: b(2.5), x: 1050, y: -220, flying: true, size: 130 },
  { f: b(4), x: 1330, y: 112, flying: true, size: 130 }, // lands on the receipts
  { f: b(6), x: 1330, y: 112, flying: false, size: 130 },
  { f: b(7.5), x: 1640, y: 266, flying: true, size: 120 }, // on top of the folder
  { f: b(10.3), x: 1640, y: 266, flying: false, size: 120 },
  { f: b(11.2), x: 2200, y: -160, flying: true, size: 110 }, // out, past the real screen
  { f: b(12.6), x: -200, y: -160, flying: false, size: 110 }, // round, unseen
  { f: b(14), x: 70, y: 176, flying: true, size: 110 }, // above the sentence
  { f: b(31), x: 70, y: 176, flying: false, size: 110 },
  { f: b(32.5), x: PERCH_END.x, y: PERCH_END.y, flying: true, size: 150 }, // above the name
  { f: b(35.5), x: PERCH_END.x, y: PERCH_END.y, flying: false, size: 150 },
  { f: b(38), x: 2150, y: -260, flying: true, size: 100 }, // and away
];
// Pecks, as on the site: when it has landed, and when a value lands.
const PECKS = [b(5), b(9), b(17), b(19.5), b(23), b(25), b(29.75), b(34)];

const Bird: React.FC = () => {
  const frame = useCurrentFrame();
  const f = ROUTE.map((s) => s.f);
  const x = at(frame, f, ROUTE.map((s) => s.x));
  const y = at(frame, f, ROUTE.map((s) => s.y));
  const size = at(frame, f, ROUTE.map((s) => s.size));
  // Flying from a stop to the next one that was reached with `flying`.
  const flying = ROUTE.some((s, i) => i > 0 && s.flying && frame > ROUTE[i - 1].f && frame < s.f);
  const peck = PECKS.reduce((turn, when) => {
    const t = frame - when;
    if (t < 0 || t >= 10) return turn;
    return Math.floor(t / 2.5) % 2 === 0 ? 16 : 3;
  }, 0);
  const bob = flying ? Math.sin(frame / 2.2) * 7 : 0;
  const lean = flying ? -10 : peck;
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y + bob,
        transformOrigin: "50% 100%",
        transform: `rotate(${lean}deg)`,
        filter: "drop-shadow(0 8px 10px rgba(60,45,30,.18))",
      }}
    >
      <Mus size={size} flying={flying} frame={frame} />
    </div>
  );
};

// -- Text --------------------------------------------------------------------------

const Title: React.FC<{
  lines: { text: string; from: number; blue?: boolean }[];
  to: number;
  size?: number;
  width?: number;
  top?: number;
  center?: boolean;
  left?: number;
}> = ({ lines, to, size = 118, width = 1020, top = 300, center = false, left = 96 }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: center ? 0 : left, top, width: center ? 1920 : width, textAlign: center ? "center" : "left" }}>
      {lines.map((line) => {
        const opacity = Math.min(at(frame, [line.from, line.from + 7], [0, 1]), at(frame, [to - 5, to], [1, 0]));
        const y = at(frame, [line.from, line.from + 14], [36, 0]);
        return (
          <div
            key={line.text}
            style={{
              fontSize: size,
              lineHeight: 1.08,
              fontWeight: 800,
              letterSpacing: -3.5,
              color: line.blue ? C.primary : C.text,
              opacity,
              transform: `translateY(${y}px)`,
            }}
          >
            {line.text}
          </div>
        );
      })}
    </div>
  );
};

// -- Scene 1 and 2: the pile, and the folder -----------------------------------------

// The three receipts of the film, a tidy fan.
const PILE = [
  { x: 1040, y: 270, r: -9, i: 0, land: 0 },
  { x: 1270, y: 225, r: 3, i: 1, land: b(0.75) },
  { x: 1500, y: 280, r: 11, i: 2, land: b(1.5) },
];

const FOLDER = { x: 1060, y: 380, w: 760, h: 330 };

const Pile: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <>
      {PILE.map((p, n) => {
        const drop = spring({ frame: frame - p.land, fps, config: { damping: 14, stiffness: 170 } });
        const go = at(frame, [b(6) + n * 5, b(6) + n * 5 + 16], [0, 1]);
        const target = { x: FOLDER.x + 140, y: FOLDER.y + 90 };
        const x = interpolate(go, [0, 1], [p.x, target.x]);
        const y = interpolate(go, [0, 1], [p.y, target.y]) - Math.sin(go * Math.PI) * 120;
        const scale = interpolate(go, [0, 1], [0.44, 0.06]);
        if (go >= 1) return null;
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
              transform: `scale(${scale}) rotate(${p.r * (1 - go) + (1 - drop) * 30}deg)`,
              filter: "drop-shadow(0 18px 26px rgba(60,45,30,.22))",
            }}
          />
        );
      })}
    </>
  );
};

const FolderCard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: frame - SCENE.folder, fps, config: { damping: 15 } });
  const leave = at(frame, [b(10.4), b(11)], [0, 1]);
  const count = Math.min(3, Math.max(0, Math.floor((frame - (b(6) + 16)) / 5) + 1));
  return (
    <div
      style={{
        position: "absolute",
        left: FOLDER.x,
        top: FOLDER.y,
        width: FOLDER.w,
        height: FOLDER.h,
        padding: "48px 56px",
        boxSizing: "border-box",
        background: C.surface,
        borderRadius: 32,
        boxShadow: SHADOW,
        opacity: pop * (1 - leave),
        transform: `scale(${pop * (1 - 0.2 * leave)}) translateY(${-160 * leave}px)`,
      }}
    >
      <svg width="104" height="104" viewBox="0 0 24 24" fill={C.primarySoft} stroke={C.primary} strokeWidth="1.5">
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
      </svg>
      <div style={{ fontSize: 58, fontWeight: 800, color: C.text, letterSpacing: -1.5, marginTop: 8 }}>
        Huismus bonnetjes
      </div>
      <div style={{ fontSize: 42, color: C.muted, marginTop: 6 }}>
        Dropbox · {count} {count === 1 ? "foto" : "foto's"}
      </div>
    </div>
  );
};

// -- The real screens ----------------------------------------------------------------

const W = data.viewport.width;
const H = data.viewport.height;
const items = data.items;
const first = items[0];
const photo = first.boxes.photo;
const CLOSE_IN = b(13);

/** The real Overzicht, whole, with its notice: the receipts have arrived. */
const Overview: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < SCENE.read - 2 || frame > CLOSE_IN + 4) return null;
  const s = at(frame, [SCENE.read - 2, SCENE.read + 10], [0.68, 0.72]);
  const opacity = Math.min(at(frame, [SCENE.read - 2, SCENE.read + 5], [0, 1]), at(frame, [CLOSE_IN - 3, CLOSE_IN + 4], [1, 0]));
  const [x, y, w, h] = data.overview.boxes.banner;
  const ring = between(frame, SCENE.read + 10, CLOSE_IN + 4, 8);
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
          transform: `translate(1370px, 540px) scale(${s}) translate(${-W / 2}px, ${-H / 2}px)`,
          borderRadius: 20,
          overflow: "hidden",
          boxShadow: SHADOW,
          background: C.bg,
        }}
      >
        <Img src={opname(data.overview.file)} style={{ position: "absolute", left: 0, top: 0, width: W, height: H }} />
        <div
          style={{
            position: "absolute",
            left: x - 7,
            top: y - 7,
            width: w + 14,
            height: h + 14,
            borderRadius: 16,
            border: `5px solid ${C.accent}`,
            boxShadow: `0 0 0 9px ${C.accentSoft}`,
            opacity: ring,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

// Verwerken without its menu: the real page from here on to the right.
const PAGE_LEFT = 280;
// Two calm framings, each leaving a column free on the left for a sentence.
const framing = (left: number, s: number, top: number) => ({
  x: PAGE_LEFT + (960 - left) / s,
  y: top + 540 / s,
  s,
});
const READING = framing(443, 1.3, 106);
const CHECKING = framing(852, 0.94, 18);

type Cam = { f: number; x: number; y: number; s: number };
const CAMERA: Cam[] = [
  { f: CLOSE_IN, ...READING },
  { f: b(21), ...READING },
  { f: b(22.25), ...CHECKING },
  { f: SCENE.end, ...CHECKING },
];
const camera = (frame: number) => {
  const f = CAMERA.map((k) => k.f);
  return {
    x: at(frame, f, CAMERA.map((k) => k.x)),
    y: at(frame, f, CAMERA.map((k) => k.y)),
    s: at(frame, f, CAMERA.map((k) => k.s)),
  };
};

// Klopt: on the beat. Each receipt's card leaves, the next is underneath.
const KLOPT = [b(23), b(25), b(27)];
const SWIPE = 12;
const FLIGHT = 13;
const total = first.receipt.totalAt;
// Each value lifts off the receipt and lands in its field; `y` is where on
// the photo it comes from. The fields in `also` uncover at the same moment.
const VALUES = [
  { key: "supplier", text: first.receipt.supplier, from: b(16), y: 0.17, also: ["date", "description", "line"] },
  { key: "amount", text: `€ ${first.receipt.total}`, from: b(17.5), y: total, also: ["category", "total"] },
  { key: "vat", text: `btw € ${first.receipt.vat}`, from: b(19), y: total + 0.075, also: [] as string[] },
] as const;
const NOTICE_SHOWS = b(20.25);

const coverBox = (key: keyof typeof first.boxes): Box => {
  const [x, y, w, h] = first.boxes[key];
  // "Totaal" is plain text, not an input; a select keeps its arrow.
  if (key === "total") return [x - 8, y - 5, w + 16, h + 10];
  if (key === "category") return [x, y, w - 40, h];
  return [x, y, w, h];
};

/** A field's real contents, hidden until the value arrives, then wiped open. */
const FieldCover: React.FC<{ box: Box; from: number }> = ({ box, from }) => {
  const frame = useCurrentFrame();
  const [x, y, w, h] = box;
  const wipe = at(frame, [from, from + 9], [0, 100]);
  return (
    <div
      style={{
        position: "absolute",
        left: x + 2,
        top: y + 2,
        width: w - 4,
        height: h - 4,
        borderRadius: 7,
        background: C.surface,
        clipPath: `inset(0 0 0 ${wipe}%)`,
      }}
    />
  );
};

const PageImage: React.FC<{ file: string }> = ({ file }) => (
  <Img src={opname(file)} style={{ position: "absolute", left: 0, top: 0, width: W, height: H }} />
);

const SwipedCard: React.FC<{ file: string; at: number }> = ({ file, at: when }) => {
  const frame = useCurrentFrame();
  const go = interpolate(frame - when - 3, [0, SWIPE], [0, 1], {
    easing: EASE,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  if (frame < when || go >= 1) return null;
  const x = first.boxes.head[0] - 8;
  const y = first.boxes.notice[1] - 8;
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width: W - x,
        height: H - y,
        overflow: "hidden",
        transform: `translateX(${go * 1300}px)`,
        background: C.bg,
      }}
    >
      <Img src={opname(file)} style={{ position: "absolute", left: -x, top: -y, width: W, height: H }} />
    </div>
  );
};

const KloptPress: React.FC<{ box: Box; at: number }> = ({ box, at: when }) => {
  const frame = useCurrentFrame();
  const [x, y, w, h] = box;
  const t = frame - when;
  if (frame > when + 16 || frame < when - b(1)) return null;
  const glow = between(frame, when - b(1), when + 3, 5);
  const ripple = interpolate(t, [0, 16], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: x - 8,
          top: y - 8,
          width: w + 16,
          height: h + 16,
          borderRadius: 14,
          border: `5px solid ${C.accent}`,
          opacity: glow,
        }}
      />
      {t >= 0 && (
        <div
          style={{
            position: "absolute",
            left: x + w / 2 - 15 - 80 * ripple,
            top: y + h / 2 - 15 - 80 * ripple,
            width: 30 + 160 * ripple,
            height: 30 + 160 * ripple,
            borderRadius: "50%",
            border: `4px solid ${C.primary}`,
            opacity: 1 - ripple,
          }}
        />
      )}
    </>
  );
};

/** The real Verwerken, and then the real "Niets meer te verwerken". */
const Verwerken: React.FC = () => {
  const frame = useCurrentFrame();
  const leave = at(frame, [SCENE.end - 4, SCENE.end + 4], [0, 1]);
  if (frame < CLOSE_IN - 3 || leave >= 1) return null;
  const cam = camera(frame);
  const appear = at(frame, [CLOSE_IN - 3, CLOSE_IN + 5], [0, 1]);
  const baseIndex = KLOPT.filter((when) => frame >= when).length;
  const base = baseIndex < items.length ? items[baseIndex].file : data.done.file;
  const scanFrom = b(13.75);
  const scanTo = b(15.75);
  const scan = interpolate(frame, [scanFrom, scanTo], [0.08, 0.62], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const notice = first.boxes.notice;
  return (
    <AbsoluteFill style={{ opacity: appear * (1 - leave) }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: W,
          height: H,
          transformOrigin: "0 0",
          transform: `translate(960px, 540px) scale(${cam.s}) translate(${-cam.x}px, ${-cam.y}px)`,
          clipPath: `inset(0 0 0 ${PAGE_LEFT}px round 22px)`,
        }}
      >
        <PageImage file={base} />
        {items.map((item, i) => (
          <SwipedCard key={item.file} file={item.file} at={KLOPT[i]} />
        ))}
        {frame < SCENE.check &&
          VALUES.flatMap((value) => {
            const from = value.from + FLIGHT - 2;
            return [value.key, ...value.also].map((key) => (
              <FieldCover key={key} box={coverBox(key as keyof typeof first.boxes)} from={from} />
            ));
          })}
        {frame < NOTICE_SHOWS + 12 && (
          <div
            style={{
              position: "absolute",
              left: notice[0] - 2,
              top: notice[1] - 2,
              width: notice[2] + 4,
              height: notice[3] + 4,
              background: C.bg,
              opacity: at(frame, [NOTICE_SHOWS, NOTICE_SHOWS + 12], [1, 0]),
            }}
          />
        )}
        <div style={{ opacity: between(frame, scanFrom - 5, scanTo + 5, 5) }}>
          <div
            style={{
              position: "absolute",
              left: photo[0],
              top: photo[1] + photo[3] * scan - 70,
              width: photo[2],
              height: 70,
              background: `linear-gradient(to bottom, transparent, ${C.accent}66)`,
              borderBottom: `4px solid ${C.accent}`,
            }}
          />
        </div>
        {frame < SCENE.check &&
          VALUES.map((value) => (
            <div
              key={value.key}
              style={{
                position: "absolute",
                left: photo[0] + photo[2] * 0.17,
                top: photo[1] + photo[3] * value.y - 17,
                width: photo[2] * 0.68,
                height: 34,
                borderRadius: 6,
                background: C.accent,
                mixBlendMode: "multiply",
                opacity: 0.5 * between(frame, value.from - 4, value.from + FLIGHT, 4),
              }}
            />
          ))}
        {items.map((item, i) => (
          <KloptPress key={item.file} box={item.boxes.klopt} at={KLOPT[i]} />
        ))}
      </div>
    </AbsoluteFill>
  );
};

const ValueChip: React.FC<{ value: (typeof VALUES)[number] }> = ({ value }) => {
  const frame = useCurrentFrame();
  const from = value.from;
  if (frame < from - 5 || frame > from + FLIGHT + 3) return null;
  const cam = camera(frame);
  const toScreen = (x: number, y: number) => ({ x: 960 + (x - cam.x) * cam.s, y: 540 + (y - cam.y) * cam.s });
  const field = first.boxes[value.key];
  const start = toScreen(photo[0] + photo[2] / 2, photo[1] + photo[3] * value.y);
  const end = toScreen(field[0] + field[2] * 0.5, field[1] + field[3] / 2);
  const lift = at(frame, [from - 5, from], [0, 1]);
  const go = at(frame, [from, from + FLIGHT], [0, 1]);
  const fade = at(frame, [from + FLIGHT - 1, from + FLIGHT + 3], [1, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: interpolate(go, [0, 1], [start.x, end.x]),
        top: interpolate(go, [0, 1], [start.y, end.y]),
        transform: `translate(-50%, -50%) scale(${lift})`,
        padding: "12px 32px",
        background: C.accent,
        color: C.text,
        fontSize: 64,
        fontWeight: 800,
        letterSpacing: -1,
        borderRadius: 18,
        whiteSpace: "nowrap",
        boxShadow: "0 16px 40px rgba(134,71,15,.35)",
        opacity: fade,
      }}
    >
      {value.text}
    </div>
  );
};

// -- The closing card ----------------------------------------------------------------

const EndCard: React.FC = () => {
  const frame = useCurrentFrame();
  const chips = ["Draait op je eigen computer", "Je eigen cloud", "Je eigen AI"];
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: 400, flexDirection: "column" }}>
      <div
        style={{
          fontSize: 190,
          fontWeight: 800,
          letterSpacing: -7,
          lineHeight: 1,
          color: C.text,
          opacity: at(frame, [SCENE.end, SCENE.end + 8], [0, 1]),
          transform: `translateY(${at(frame, [SCENE.end, SCENE.end + 12], [40, 0])}px)`,
        }}
      >
        Huismus
      </div>
      <div
        style={{
          fontSize: 64,
          fontWeight: 600,
          color: C.muted,
          marginTop: 16,
          letterSpacing: -1,
          opacity: at(frame, [b(31.5), b(32.25)], [0, 1]),
        }}
      >
        Facturen en bonnetjes voor zzp'ers
      </div>
      <div style={{ display: "flex", gap: 22, marginTop: 56 }}>
        {chips.map((chip, i) => {
          const t = at(frame, [b(32.5) + i * 5, b(32.5) + i * 5 + 10], [0, 1]);
          return (
            <div
              key={chip}
              style={{
                padding: "18px 34px",
                borderRadius: 999,
                background: C.primarySoft,
                color: C.primary,
                fontSize: 44,
                fontWeight: 700,
                opacity: t,
                transform: `translateY(${(1 - t) * 18}px)`,
              }}
            >
              {chip}
            </div>
          );
        })}
      </div>
      <div
        style={{
          fontSize: 66,
          fontWeight: 800,
          letterSpacing: -1,
          color: C.primary,
          marginTop: 44,
          opacity: at(frame, [b(34), b(34.75)], [0, 1]),
        }}
      >
        huismus.arnekrijnsen.com
      </div>
    </AbsoluteFill>
  );
};

// -- Sound, on the same beats --------------------------------------------------------

const Sfx: React.FC<{ file: string; at: number; volume: number }> = ({ file, at: when, volume }) => (
  <Sequence from={Math.round(when)} durationInFrames={20}>
    <Audio src={staticFile(file)} volume={volume} />
  </Sequence>
);

// -- The film ------------------------------------------------------------------------

export const Bonnetjes: React.FC = () => {
  const frame = useCurrentFrame();
  const brand = Math.min(at(frame, [0, 10], [0, 1]), at(frame, [CLOSE_IN - 4, CLOSE_IN + 4], [1, 0]));
  const fadeOut = at(frame, [DURATION - 8, DURATION], [0, 1]);
  return (
    <AbsoluteFill
      style={{
        fontFamily: FONT,
        background: `radial-gradient(1500px 950px at 72% 32%, ${C.surface} 0%, ${C.bg} 55%, ${C.surface2} 100%)`,
      }}
    >
      <Audio
        src={opname("muziek.wav")}
        volume={(f) =>
          interpolate(f, [DURATION - 25, DURATION], [0.9, 0.2], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })
        }
      />
      <div style={{ position: "absolute", left: 96, top: 76, display: "flex", alignItems: "center", gap: 18, opacity: brand }}>
        <Mus size={72} />
        <span style={{ fontSize: 54, fontWeight: 800, color: C.text, letterSpacing: -1 }}>
          Huismus <span style={{ fontWeight: 600, color: C.muted }}>voor zzp'ers</span>
        </span>
      </div>
      <Title
        lines={[
          { text: "Bonnetjes", from: 3 },
          { text: "overtypen?", from: 8 },
          { text: "Hoeft niet meer.", from: b(4), blue: true },
        ]}
        to={SCENE.folder}
      />
      <Title
        lines={[
          { text: "Foto in je", from: SCENE.folder - 1 },
          { text: "eigen cloudmap.", from: SCENE.folder + 1, blue: true },
        ]}
        to={SCENE.read}
      />
      <Title
        lines={[
          { text: "Huismus", from: SCENE.read - 1 },
          { text: "haalt ze op.", from: SCENE.read, blue: true },
        ]}
        to={CLOSE_IN + 2}
        width={760}
      />
      {frame < b(11.5) && (
        <>
          <FolderCard />
          <Pile />
        </>
      )}
      <Overview />
      <Verwerken />
      {VALUES.map((value) => (
        <ValueChip key={value.key} value={value} />
      ))}
      <Title
        lines={[
          { text: "Jouw", from: CLOSE_IN },
          { text: "eigen AI", from: CLOSE_IN },
          { text: "leest ze.", from: CLOSE_IN, blue: true },
        ]}
        to={SCENE.check + 2}
        width={380}
        size={92}
        left={52}
      />
      <Title
        lines={[
          { text: "Jij zegt", from: SCENE.check + 2 },
          { text: "alleen: Klopt.", from: SCENE.check + 2, blue: true },
        ]}
        to={SCENE.done}
        width={760}
        size={104}
        left={64}
      />
      <Title
        lines={[
          { text: "Drie bonnetjes.", from: SCENE.done },
          { text: "Klaar.", from: SCENE.done, blue: true },
        ]}
        to={SCENE.end}
        width={760}
        size={104}
        left={64}
      />
      {frame >= SCENE.end && <EndCard />}
      <Bird />
      <AbsoluteFill style={{ background: C.bg, opacity: fadeOut }} />
      {PILE.map((p) => (
        <Sfx key={p.land} file="geluiden/click_002.ogg" at={p.land + 8} volume={0.5} />
      ))}
      {VALUES.map((value) => (
        <Sfx key={value.key} file="opname/pop.wav" at={value.from + FLIGHT - 2} volume={0.5} />
      ))}
      {KLOPT.map((when) => (
        <React.Fragment key={when}>
          <Sfx file="geluiden/click_001.ogg" at={when} volume={0.7} />
          <Sfx file="opname/woesj.wav" at={when + 3} volume={0.5} />
        </React.Fragment>
      ))}
    </AbsoluteFill>
  );
};
