// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The receipts clip, 20 seconds. A pile of receipts, a sparrow, your own
 * cloud folder; then the real Verwerken screen, its fields filling in from
 * the receipt; then Klopt, Klopt, Klopt, and the sparrow flies off.
 *
 * The real Verwerken screen comes from Huismus on made-up data
 * (scripts/promo_film.py, public/opname/). On a phone a whole screen is
 * unreadable, so the film then moves in to a close-up of that same screen,
 * drawn large in Huismus's own look: the receipt, three fields, Klopt.
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
  { f: b(11.2), x: 2200, y: -120, flying: true, size: 110 }, // out, past the real screen
  { f: b(12.6), x: 2200, y: -120, flying: false, size: 110 },
  { f: b(14), x: 1660, y: 26, flying: true, size: 110 }, // on top of the close-up
  { f: b(28), x: 1660, y: 26, flying: false, size: 110 },
  { f: b(29), x: 900, y: 262, flying: true, size: 130 }, // above "Drie bonnetjes"
  { f: b(31), x: 900, y: 262, flying: false, size: 130 },
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
}> = ({ lines, to, size = 118, width = 1020, top = 300, center = false }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ position: "absolute", left: center ? 0 : 96, top, width: center ? 1920 : width, textAlign: center ? "center" : "left" }}>
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

// -- The real screen, then the close-up -----------------------------------------------

const W = data.viewport.width;
const H = data.viewport.height;
const items = data.items;
const first = items[0];
const CLOSE_IN = b(13);

/** A field's contents hidden: Huismus has not read this receipt yet. */
const Blank: React.FC<{ box: Box; right?: number }> = ({ box, right = 0 }) => (
  <div
    style={{
      position: "absolute",
      left: box[0] + 2,
      top: box[1] + 2,
      width: box[2] - 4 - right,
      height: box[3] - 4,
      borderRadius: 7,
      background: C.surface,
    }}
  />
);

/** The real Verwerken, whole and uncropped, beside a sentence. */
const RealScreen: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < SCENE.read - 2 || frame > CLOSE_IN + 4) return null;
  const s = at(frame, [SCENE.read - 2, SCENE.read + 10], [0.68, 0.72]);
  const opacity = Math.min(at(frame, [SCENE.read - 2, SCENE.read + 5], [0, 1]), at(frame, [CLOSE_IN - 3, CLOSE_IN + 4], [1, 0]));
  const boxes = first.boxes;
  const fields: (keyof typeof boxes)[] = ["date", "supplier", "description", "line", "amount", "vat"];
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
        <Img src={opname(first.file)} style={{ position: "absolute", left: 0, top: 0, width: W, height: H }} />
        {fields.map((key) => (
          <Blank key={key} box={boxes[key]} />
        ))}
        <Blank box={boxes.category} right={40} />
        <Blank box={[boxes.total[0] - 8, boxes.total[1] - 5, boxes.total[2] + 16, boxes.total[3] + 10]} />
        <div
          style={{
            position: "absolute",
            left: boxes.notice[0] - 2,
            top: boxes.notice[1] - 2,
            width: boxes.notice[2] + 4,
            height: boxes.notice[3] + 4,
            background: C.bg,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

// The close-up's layout, in film pixels.
const PAPER = { x: 76, y: 150, w: 688, h: 905 };
const RECEIPT_CARD = { x: 70, y: 130, w: 700, h: 860 };
const FORM_CARD = { x: 810, y: 130, w: 1040, h: 860 };
const ROW_X = FORM_CARD.x + 52;
const ROW_W = FORM_CARD.w - 104;
const rowTop = (i: number) => 372 + 152 * i;
const BOX_H = 92;

// Klopt: on the beat. Each receipt leaves to the left, the next comes in.
const KLOPT = [b(23), b(25), b(27)];
const SWIPE = 10;
// When Huismus has finished reading the first receipt, its values land.
const READ = { supplier: b(16), amount: b(17.5), vat: b(19) };
const FLIGHT = 13;
const LOOKS_RIGHT = b(20.5); // the status line changes to "Klopt alles?"

const rowsOf = (item: (typeof items)[number]) => [
  { key: "supplier" as const, label: "Leverancier", value: item.receipt.supplier, y: 0.11 },
  { key: "amount" as const, label: "Bedrag", value: `€ ${item.receipt.total}`, y: item.receipt.paperTotalAt },
  { key: "vat" as const, label: "Btw ter info", value: `€ ${item.receipt.vat}`, y: item.receipt.paperTotalAt + 0.098 },
];

const Close: React.FC<{ index: number }> = ({ index }) => {
  const frame = useCurrentFrame();
  const item = items[index];
  const isFirst = index === 0;
  const enter = isFirst ? CLOSE_IN : KLOPT[index - 1] + 3;
  const leave = KLOPT[index] + 3;
  if (frame < enter - 1 || frame > leave + SWIPE + 1) return null;
  const inT = isFirst ? 0 : at(frame, [enter, enter + SWIPE], [1, 0]);
  const outT = at(frame, [leave, leave + SWIPE], [0, 1]);
  const appear = isFirst ? at(frame, [enter, enter + 8], [0, 1]) : 1;
  const scale = isFirst ? at(frame, [enter, enter + 12], [0.96, 1]) : 1;
  const x = inT * 2100 - outT * 2300;
  const rotate = inT * 5 - outT * 6;
  const reading = isFirst && frame < LOOKS_RIGHT;
  const scan = isFirst
    ? interpolate(frame, [b(13.75), b(15.75)], [0.06, 0.62], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : 0;
  const scanOn = isFirst ? between(frame, b(13.75), b(15.9), 5) : 0;
  const glow = between(frame, KLOPT[index] - b(1), KLOPT[index] + 3, 5);
  const t = frame - KLOPT[index];
  const ripple = interpolate(t, [0, 16], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const pressed = t >= 0 && t < 5;
  return (
    <AbsoluteFill style={{ opacity: appear, transform: `translateX(${x}px) rotate(${rotate}deg) scale(${scale})` }}>
      <div
        style={{
          position: "absolute",
          left: RECEIPT_CARD.x,
          top: RECEIPT_CARD.y,
          width: RECEIPT_CARD.w,
          height: RECEIPT_CARD.h,
          background: C.surface3,
          borderRadius: 28,
          boxShadow: SHADOW,
          overflow: "hidden",
        }}
      >
        <Img
          src={opname(item.receipt.file)}
          style={{
            position: "absolute",
            left: PAPER.x - RECEIPT_CARD.x,
            top: PAPER.y - RECEIPT_CARD.y,
            width: PAPER.w,
            height: PAPER.h,
            filter: "drop-shadow(0 14px 22px rgba(60,45,30,.25))",
          }}
        />
        {isFirst &&
          rowsOf(item).map((row) => (
            <div
              key={row.key}
              style={{
                position: "absolute",
                left: 24,
                width: RECEIPT_CARD.w - 48,
                top: PAPER.y - RECEIPT_CARD.y + PAPER.h * row.y - 28,
                height: 56,
                borderRadius: 10,
                background: C.accent,
                mixBlendMode: "multiply",
                opacity: 0.45 * between(frame, READ[row.key] - 4, READ[row.key] + FLIGHT, 4),
              }}
            />
          ))}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: PAPER.y - RECEIPT_CARD.y + PAPER.h * scan - 110,
            width: RECEIPT_CARD.w,
            height: 110,
            background: `linear-gradient(to bottom, transparent, ${C.accent}66)`,
            borderBottom: `6px solid ${C.accent}`,
            boxShadow: `0 6px 24px ${C.accent}`,
            opacity: scanOn,
          }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: FORM_CARD.x,
          top: FORM_CARD.y,
          width: FORM_CARD.w,
          height: FORM_CARD.h,
          background: C.surface,
          borderRadius: 28,
          boxShadow: SHADOW,
        }}
      />
      <div style={{ position: "absolute", left: ROW_X, top: 166, display: "flex", alignItems: "center", gap: 26 }}>
        <span style={{ fontSize: 76, fontWeight: 800, letterSpacing: -2, color: C.text }}>Verwerken</span>
        <span
          style={{
            padding: "8px 26px",
            borderRadius: 999,
            background: C.surface2,
            fontSize: 50,
            fontWeight: 700,
            color: C.muted,
          }}
        >
          {index + 1} van {items.length}
        </span>
      </div>
      <div
        style={{
          position: "absolute",
          left: ROW_X,
          top: 276,
          width: ROW_W,
          height: 78,
          display: "flex",
          alignItems: "center",
          gap: 20,
          fontSize: 54,
          fontWeight: 700,
          letterSpacing: -1,
          color: C.primary,
        }}
      >
        {reading ? (
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              border: `6px solid ${C.primarySoft}`,
              borderTopColor: C.primary,
              transform: `rotate(${frame * 12}deg)`,
            }}
          />
        ) : (
          <svg width="52" height="52" viewBox="0 0 24 24" fill="none" stroke={C.primary} strokeWidth="2.6">
            <path d="m5 12.5 4.5 4.5L19 7.5" />
          </svg>
        )}
        {reading ? "Jouw eigen AI leest hem…" : "Klopt alles?"}
      </div>
      {rowsOf(item).map((row, i) => {
        const landsAt = READ[row.key] + FLIGHT - 1;
        const shown = !isFirst || frame >= landsAt;
        const lit = isFirst && frame >= landsAt && frame < landsAt + 8;
        return (
          <div key={row.key}>
            <div style={{ position: "absolute", left: ROW_X, top: rowTop(i), fontSize: 38, fontWeight: 650, color: C.muted }}>
              {row.label}
            </div>
            <div
              style={{
                position: "absolute",
                left: ROW_X,
                top: rowTop(i) + 48,
                width: ROW_W,
                height: BOX_H,
                boxSizing: "border-box",
                padding: "0 30px",
                display: "flex",
                alignItems: "center",
                justifyContent: row.key === "supplier" ? "flex-start" : "flex-end",
                background: C.surface,
                border: `3px solid ${lit ? C.accent : C.surface3}`,
                borderRadius: 18,
                fontSize: 58,
                fontWeight: 750,
                letterSpacing: -1,
                color: C.text,
              }}
            >
              <span style={{ opacity: shown ? 1 : 0 }}>{row.value}</span>
            </div>
          </div>
        );
      })}
      <div
        style={{
          position: "absolute",
          left: FORM_CARD.x + FORM_CARD.w - 52 - 300,
          top: FORM_CARD.y + FORM_CARD.h - 40 - 108,
          width: 300,
          height: 108,
          borderRadius: 22,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: C.primary,
          color: C.surface,
          fontSize: 62,
          fontWeight: 800,
          letterSpacing: -1,
          transform: `scale(${pressed ? 0.94 : 1})`,
          boxShadow: `0 0 0 ${glow * 12}px ${C.accent}`,
        }}
      >
        Klopt
      </div>
      {t >= 0 && t < 16 && (
        <div
          style={{
            position: "absolute",
            left: FORM_CARD.x + FORM_CARD.w - 52 - 150 - 40 - 130 * ripple,
            top: FORM_CARD.y + FORM_CARD.h - 40 - 54 - 40 - 130 * ripple,
            width: 80 + 260 * ripple,
            height: 80 + 260 * ripple,
            borderRadius: "50%",
            border: `6px solid ${C.primary}`,
            opacity: 1 - ripple,
          }}
        />
      )}
    </AbsoluteFill>
  );
};

/** A value lifts off the receipt and lands in its field, at the size it has there. */
const ValueChip: React.FC<{ row: ReturnType<typeof rowsOf>[number]; index: number }> = ({ row, index }) => {
  const frame = useCurrentFrame();
  const from = READ[row.key];
  if (frame < from - 5 || frame > from + FLIGHT + 3) return null;
  const startX = PAPER.x + PAPER.w / 2;
  const startY = PAPER.y + PAPER.h * row.y;
  const right = row.key !== "supplier";
  const endX = right ? ROW_X + ROW_W - 170 : ROW_X + 260;
  const endY = rowTop(index) + 48 + BOX_H / 2;
  const lift = at(frame, [from - 5, from], [0, 1]);
  const go = at(frame, [from, from + FLIGHT], [0, 1]);
  const fade = at(frame, [from + FLIGHT - 1, from + FLIGHT + 3], [1, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: interpolate(go, [0, 1], [startX, endX]),
        top: interpolate(Math.min(go * 2, 1), [0, 1], [startY, endY]),
        transform: `translate(-50%, -50%) scale(${lift})`,
        padding: "10px 30px",
        background: C.accent,
        color: C.text,
        fontSize: 58,
        fontWeight: 800,
        letterSpacing: -1,
        borderRadius: 18,
        whiteSpace: "nowrap",
        boxShadow: "0 16px 40px rgba(134,71,15,.35)",
        opacity: fade,
      }}
    >
      {row.value}
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
      <RealScreen />
      {items.map((item, i) => (
        <Close key={item.file} index={i} />
      ))}
      {rowsOf(first).map((row, i) => (
        <ValueChip key={row.key} row={row} index={i} />
      ))}
      <Title
        lines={[
          { text: "Drie bonnetjes.", from: SCENE.done - 3 },
          { text: "Klaar.", from: SCENE.done, blue: true },
        ]}
        to={SCENE.end}
        center
        top={400}
        size={150}
      />
      {frame >= SCENE.end && <EndCard />}
      <Bird />
      <AbsoluteFill style={{ background: C.bg, opacity: fadeOut }} />
      {PILE.map((p) => (
        <Sfx key={p.land} file="geluiden/click_002.ogg" at={p.land + 8} volume={0.5} />
      ))}
      {Object.values(READ).map((when) => (
        <Sfx key={when} file="opname/pop.wav" at={when + FLIGHT - 2} volume={0.5} />
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
