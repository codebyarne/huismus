// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The overview film, about a minute: what Huismus is, for whom, and what you
 * do with it, in the order of the site's home page (huismus/templates/site/).
 *
 * The script is overzicht.json: per shot when it starts, how long it lasts
 * and what the voice says. scripts/promo_geluid.py makes the voice (one file
 * per shot, so another voice goes in without editing anything here), the
 * subtitles and the music from it. The screens are real, from Huismus on
 * made-up data (scripts/promo_film.py, public/opname/).
 *
 * Props: `stem` (the voice, with the music quieter under it) and
 * `ondertitels` (the Dutch subtitles burnt in).
 */
import React from "react";
import { AbsoluteFill, Audio, Img, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import data from "../public/opname/opname.json";
import cues from "../public/opname/ondertitels.json";
import script from "./overzicht.json";
import { at, BACKGROUND, Box, Cam, camera, Check, fadeInOut, Logo, opname, Press, Ring, Toast } from "./delen";
import { C, DISPLAY, FONT, SHADOW } from "./huismus";

export type Props = { stem: boolean; ondertitels: boolean };

const FPS = 30;
const frames = (seconds: number) => Math.round(seconds * FPS);
// Where each shot starts, in frames, by the number in its id ("03-overstappen" → S[3]).
const S: number[] = [0, ...script.shots.map((shot) => frames(shot.start))];
const last = script.shots[script.shots.length - 1];
export const DURATION = frames(last.start + last.duur);
S.push(DURATION);

// -- The stage: the app's window, right of the text ---------------------------------

// With subtitles the stage sits higher, and they go under it, not over it.
const STAGE = { left: 600, width: 1240, height: 820 };
const stageTop = (ondertitels: boolean) => (ondertitels ? 84 : 130);
const tour = data.tour;
const mb = data.import;
// The app without its menu fills the stage: the content is what a shot is about.
const CONTENT_X = (244 + data.viewport.width) / 2;
const FULL = STAGE.width / (data.viewport.width - 244 + 8);
/** The camera on the content, with `y` at the top of the stage. */
const from = (y: number, s = FULL) => ({ x: CONTENT_X, y: y + STAGE.height / s / 2, s });
/** The camera that shows a box with room around it, without looking past
 * the top or the bottom of the screenshot. */
const fit = (b: Box, pad = 60, max = 1.5) => {
  const s = Math.min(STAGE.width / (b[2] + 2 * pad), STAGE.height / (b[3] + 2 * pad), max);
  const half = STAGE.height / s / 2;
  const y = Math.max(half, Math.min(b[1] + b[3] / 2, data.viewport.height - half));
  return { x: b[0] + b[2] / 2, y, s };
};

const boxes = (step: number) => tour.invoice[step].boxes as unknown as Record<string, Box>;
const draft = boxes(2);
const lines: Box = [
  draft.paper[0] + 30,
  draft.line[1] - 110,
  draft.paper[2] - 60,
  draft.total[1] + draft.total[3] - draft.line[1] + 130,
];
const dialog = boxes(3);
const issued = boxes(4);
const receipt = data.items[0];
const invoices = mb.dryRun.boxes.invoices;
// What differs from Moneybird's own totals: the top of the list in that report.
const differences: Box = [invoices[0], invoices[1] + 125, invoices[2], 330];
const moved = mb.imported.boxes;
const paperX = draft.paper[0] + draft.paper[2] / 2;
// The whole window, menu and all, with its top at the top of the stage.
const WINDOW = STAGE.width / data.viewport.width;
const WHOLE = { x: data.viewport.width / 2, y: STAGE.height / WINDOW / 2, s: WINDOW };

// Moments inside the shots, in frames.
const IMPORTED = S[3] + 232; // "Dan pas importeer je."
const TYPED = S[4] + 70;
const TOTAL = S[4] + 112;
const DIALOG = S[4] + 150;
const ISSUED = S[4] + 196;
const KLOPT = S[5] + 138;
const VAT = S[6] + 188; // "Zonder KOR ..."

const SCREENS = [
  { f: S[2], file: tour.overview.file },
  { f: S[3], file: mb.dryRun.file },
  { f: IMPORTED, file: mb.imported.file },
  { f: S[4], file: tour.invoice[0].file },
  { f: TYPED, file: tour.invoice[1].file },
  { f: TOTAL, file: tour.invoice[2].file },
  { f: DIALOG, file: tour.invoice[3].file },
  { f: ISSUED, file: tour.invoice[4].file },
  { f: S[5], file: receipt.file },
  { f: KLOPT + 8, file: data.items[1].file },
  { f: S[6], file: tour.year.file },
  { f: VAT, file: mb.vat.file },
];

const CAMERA: Cam[] = [
  // The overview: the year so far, then what there is to do.
  { f: S[2], ...WHOLE },
  { f: S[2] + 50, ...WHOLE },
  { f: S[2] + 85, ...from(24) },
  { f: S[2] + 130, ...from(24) },
  { f: S[2] + 175, ...from(190) },
  { f: S[3] - 1, ...from(190) },
  // Moneybird: the dry run, what differs, and the result.
  { f: S[3], ...from(40) },
  { f: S[3] + 80, ...from(40) },
  { f: S[3] + 125, ...fit(differences, 10) },
  { f: IMPORTED - 1, ...fit(differences, 10) },
  { f: IMPORTED, ...fit([moved.card[0], moved.steps[1] - 8, moved.card[2], 640], 30) },
  { f: S[4] - 1, ...fit([moved.card[0], moved.steps[1] - 8, moved.card[2], 640], 30) },
  // An invoice: the lines and the total, the question, and the issued invoice.
  { f: S[4], ...fit(draft.paper, 20) },
  { f: S[4] + 24, ...fit(draft.paper, 20) },
  { f: S[4] + 58, x: paperX, y: lines[1] + lines[3] / 2 - 8, s: 1.5 },
  { f: DIALOG - 1, x: paperX, y: lines[1] + lines[3] / 2 - 8, s: 1.5 },
  { f: DIALOG, ...fit(dialog.dialog, 110) },
  { f: ISSUED - 1, ...fit(dialog.dialog, 110) },
  { f: ISSUED, ...from(40) },
  { f: S[5] - 1, ...from(40) },
  // A receipt in Verwerken: the photo and what Huismus read, then Klopt.
  { f: S[5], ...from(8) },
  { f: S[5] + 70, ...from(8) },
  { f: S[5] + 115, ...from(350) },
  { f: KLOPT + 8, ...from(350) },
  { f: KLOPT + 30, ...from(8) },
  { f: S[6] - 1, ...from(8) },
  // The year: the totals, the KOR limit and the quarters, then a VAT return.
  { f: S[6], ...from(30) },
  { f: VAT - 1, ...from(30) },
  { f: VAT, ...from(50) },
  { f: S[7], ...from(50) },
];

const Stage: React.FC<{ top: number }> = ({ top }) => {
  const frame = useCurrentFrame();
  const cam = camera(frame, CAMERA);
  const slide = at(frame, [S[2], S[2] + 24], [140, 0]);
  const opacity = Math.min(at(frame, [S[2], S[2] + 16], [0, 1]), at(frame, [S[7] - 4, S[7] + 10], [1, 0]));
  return (
    <div
      style={{
        position: "absolute",
        ...STAGE,
        top,
        borderRadius: 26,
        overflow: "hidden",
        background: C.surface,
        border: `1px solid ${C.border}`,
        boxShadow: SHADOW,
        opacity,
        transform: `translateX(${slide}px)`,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: data.viewport.width,
          height: data.viewport.height,
          transformOrigin: "0 0",
          transform: `translate(${STAGE.width / 2}px, ${STAGE.height / 2}px) scale(${cam.s}) translate(${-cam.x}px, ${-cam.y}px)`,
        }}
      >
        {SCREENS.map((screen, i) => {
          const next = SCREENS[i + 1];
          if (frame < screen.f - 1 || (next && frame > next.f + 10)) return null;
          return (
            <Img
              key={screen.file}
              src={opname(screen.file)}
              style={{
                position: "absolute",
                left: 0,
                top: 0,
                width: data.viewport.width,
                height: data.viewport.height,
                opacity: i === 0 ? 1 : at(frame, [screen.f, screen.f + 8], [0, 1]),
              }}
            />
          );
        })}
        <Ring box={tour.overview.boxes.hero} from={S[2] + 92} to={S[2] + 132} radius={24} pad={6} />
        <Ring box={[draft.line[0] - 8, draft.line[1] - 4, draft.paper[2] - 150, draft.line[3] + 8]} from={TYPED + 4} to={TOTAL + 10} pad={4} />
        <Ring box={[draft.total[0], draft.total[1] - 42, draft.total[2], 40]} from={TOTAL + 6} to={DIALOG - 4} pad={6} />
        <Press box={dialog.confirm} at={ISSUED - 10} />
        <Ring box={issued.title} from={ISSUED + 8} to={S[5] - 6} pad={10} />
        <Ring box={receipt.boxes.amount} from={S[5] + 40} to={S[5] + 100} />
        <Ring box={receipt.boxes.klopt} from={KLOPT - 24} to={KLOPT + 4} pad={6} />
        <Press box={receipt.boxes.klopt} at={KLOPT} />
        <Toast text="Uitgave nagekeken." from={KLOPT + 14} to={S[6] - 8} />
        <Ring box={tour.year.boxes.totals} from={S[6] + 20} to={S[6] + 95} radius={24} pad={6} />
        <Ring box={tour.year.boxes.kor} from={S[6] + 105} to={VAT - 6} radius={24} pad={6} />
        <Ring box={mb.vat.boxes.total} from={VAT + 24} to={S[7] - 6} radius={24} pad={4} />
      </div>
    </div>
  );
};

// -- The text beside the stage ------------------------------------------------------

// `when`: the frame in the shot at which each point comes, if not evenly spread.
type Slide = { shot: number; kicker: string; title: string[]; points: string[]; when?: number[] };
const SLIDES: Slide[] = [
  {
    shot: 2,
    kicker: "Voor wie",
    title: ["Voor zzp’ers die", "het zelf doen"],
    points: ["Gratis", "Geen abonnement", "Geen account", "Met of zonder KOR"],
  },
  {
    shot: 3,
    kicker: "Overstappen",
    title: ["Neem al je", "jaren mee"],
    points: ["Eerst een proefdraai", "Elk totaal nagerekend", "Dan pas importeren"],
  },
  {
    shot: 4,
    kicker: "Facturen",
    title: ["Een factuur", "maken"],
    points: ["Kies een klant", "Typ wat je deed", "Huismus rekent het uit"],
  },
  {
    shot: 5,
    kicker: "Bonnetjes",
    title: ["Foto erin,", "jij kijkt na"],
    points: ["Een foto in een map", "Een AI naar keuze leest hem", "Jij zegt: Klopt"],
  },
  {
    shot: 6,
    kicker: "Het hele jaar",
    title: ["Btw, KOR en", "je jaar"],
    points: ["Omzet, kosten en winst", "Je KOR-grens in beeld", "Btw-bedragen per kwartaal"],
    when: [26, 105, 192],
  },
  {
    shot: 7,
    kicker: "Privacy",
    title: ["Je administratie", "is van jou"],
    points: ["Geen Huismus-server", "Geen account", "Een back-up in je eigen map"],
  },
];

const Column: React.FC<{ slide: Slide }> = ({ slide }) => {
  const frame = useCurrentFrame();
  const start = S[slide.shot];
  const end = S[slide.shot + 1];
  const shown = (delay: number) => fadeInOut(frame, start + delay, end + 2, 10);
  const rise = (delay: number) => at(frame, [start + delay, start + delay + 16], [22, 0]);
  // The points come one by one, spread over the first two thirds of the shot.
  const step = Math.min(42, ((end - start) * 0.62) / slide.points.length);
  return (
    <div style={{ position: "absolute", left: 80, top: 250, width: 480 }}>
      <div
        style={{
          fontSize: 25,
          fontWeight: 650,
          letterSpacing: 2.2,
          textTransform: "uppercase",
          color: C.primary,
          opacity: shown(4),
          transform: `translateY(${rise(4)}px)`,
        }}
      >
        {slide.kicker}
      </div>
      <div style={{ marginTop: 18, opacity: shown(8), transform: `translateY(${rise(8)}px)` }}>
        {slide.title.map((line) => (
          <div
            key={line}
            style={{ fontFamily: DISPLAY, fontSize: 62, lineHeight: 1.08, fontWeight: 700, letterSpacing: -1.2, color: C.text, whiteSpace: "nowrap" }}
          >
            {line}
          </div>
        ))}
      </div>
      <div style={{ marginTop: 44, display: "flex", flexDirection: "column", gap: 22 }}>
        {slide.points.map((point, i) => (
          <div
            key={point}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 18,
              fontSize: 32,
              fontWeight: 500,
              letterSpacing: -0.3,
              color: C.text,
              whiteSpace: "nowrap",
              opacity: shown(slide.when?.[i] ?? 26 + i * step),
              transform: `translateY(${rise(slide.when?.[i] ?? 26 + i * step)}px)`,
            }}
          >
            <Check size={38} />
            {point}
          </div>
        ))}
      </div>
    </div>
  );
};

// -- Shot 1: what it is ---------------------------------------------------------------

const Opening: React.FC = () => {
  const frame = useCurrentFrame();
  const out = at(frame, [S[2] - 12, S[2] + 2], [1, 0]);
  const underline = at(frame, [58, 84], [0, 1]);
  const line = (delay: number): React.CSSProperties => ({
    opacity: at(frame, [delay, delay + 14], [0, 1]),
    transform: `translateY(${at(frame, [delay, delay + 18], [30, 0])}px)`,
  });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", opacity: out }}>
      <Logo height={104} style={{ opacity: at(frame, [4, 18], [0, 1]) }} />
      <div
        style={{
          marginTop: 64,
          fontFamily: DISPLAY,
          fontSize: 132,
          lineHeight: 1.04,
          fontWeight: 700,
          letterSpacing: -2,
          color: C.text,
          textAlign: "center",
        }}
      >
        <div style={line(30)}>Je boekhouding op</div>
        <div style={line(38)}>
          <span style={{ position: "relative", display: "inline-block" }}>
            je eigen computer
            {/* The stripe of the site's headline: decoration only. */}
            <span
              style={{
                position: "absolute",
                left: 0,
                bottom: -6,
                height: 12,
                width: `${underline * 100}%`,
                borderRadius: 6,
                background: C.framboos,
              }}
            />
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// -- Shot 7: what happens to your data ------------------------------------------------

const SWITCHES = [
  { label: "Je back-up naar je eigen cloud", on: false },
  { label: "Een factuur via je eigen mail", on: false },
  { label: "Een bonnetje naar een AI-dienst die jij kiest", on: false },
  { label: "Je administratie aan een AI-assistent die jij koppelt", on: false },
];

const YourData: React.FC<{ top: number }> = ({ top }) => {
  const frame = useCurrentFrame();
  const opacity = fadeInOut(frame, S[7] + 4, S[8] + 2, 12);
  const slide = at(frame, [S[7] + 4, S[7] + 26], [40, 0]);
  return (
    <div
      style={{
        position: "absolute",
        left: STAGE.left + 60,
        top: top + 24,
        width: STAGE.width - 120,
        boxSizing: "border-box",
        padding: "44px 52px 30px",
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: 28,
        boxShadow: SHADOW,
        opacity,
        transform: `translateY(${slide}px)`,
      }}
    >
      <div style={{ fontFamily: DISPLAY, fontSize: 40, fontWeight: 650, letterSpacing: -0.6, color: C.text }}>
        Wat er met je gegevens gebeurt
      </div>
      <div
        style={{
          marginTop: 28,
          padding: "30px 34px",
          borderRadius: 20,
          background: C.hero,
          display: "flex",
          alignItems: "center",
          gap: 26,
        }}
      >
        <svg width="62" height="62" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <rect x="4" y="5" width="16" height="11" rx="2" />
          <path d="M2 19.5h20" />
        </svg>
        <div>
          <div style={{ fontFamily: DISPLAY, fontSize: 40, fontWeight: 700, letterSpacing: -0.6, color: "#FFFFFF" }}>Jouw computer</div>
          <div style={{ fontSize: 29, color: C.heroMuted, marginTop: 4 }}>Hier staat je hele administratie.</div>
        </div>
      </div>
      {SWITCHES.map((row, i) => {
        const shown = at(frame, [S[7] + 40 + i * 14, S[7] + 54 + i * 14], [0, 1]);
        return (
          <div
            key={row.label}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 24,
              height: 96,
              borderBottom: i < SWITCHES.length - 1 ? `1px solid ${C.border}` : "none",
              opacity: shown,
            }}
          >
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: -0.3, color: C.text }}>{row.label}</div>
              <div style={{ fontSize: 23, color: C.muted, marginTop: 2 }}>
                {row.on ? "Aan, en dat kun je uitzetten" : "Uit, tot jij het aanzet"}
              </div>
            </div>
            <div
              style={{
                width: 76,
                height: 44,
                borderRadius: 22,
                background: row.on ? C.primary : C.surface3,
                border: `1px solid ${row.on ? C.primary : C.borderStrong}`,
                position: "relative",
                flex: "none",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 5,
                  left: row.on ? 37 : 5,
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: row.on ? C.onPrimary : C.muted,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};

// -- Shot 8: the next step -------------------------------------------------------------

const Download: React.FC = () => {
  // Inside its Sequence: frame 0 is the start of the shot.
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame: frame - 8, fps, config: { damping: 14 } });
  const shown = (delay: number): React.CSSProperties => ({
    opacity: at(frame, [delay, delay + 14], [0, 1]),
    transform: `translateY(${at(frame, [delay, delay + 16], [20, 0])}px)`,
  });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
      <div style={{ opacity: Math.min(pop, 1), transform: `scale(${0.7 + 0.3 * pop})` }}>
        <Logo height={132} />
      </div>
      <div
        style={{
          marginTop: 56,
          fontFamily: DISPLAY,
          fontSize: 92,
          fontWeight: 700,
          letterSpacing: -2,
          color: C.text,
          ...shown(20),
        }}
      >
        Download Huismus gratis
      </div>
      <div style={{ marginTop: 14, fontSize: 40, color: C.muted, ...shown(30) }}>Voor Mac en Windows</div>
      <div
        style={{
          marginTop: 52,
          padding: "22px 54px",
          borderRadius: 999,
          background: C.primary,
          color: C.onPrimary,
          fontFamily: DISPLAY,
          fontSize: 60,
          fontWeight: 700,
          letterSpacing: -1,
          ...shown(44),
        }}
      >
        mijnhuismus.nl
      </div>
    </AbsoluteFill>
  );
};

// -- Subtitles ------------------------------------------------------------------------

const Subtitles: React.FC = () => {
  const seconds = useCurrentFrame() / FPS;
  const cue = cues.find((line) => seconds >= line.van && seconds < line.tot);
  if (!cue) return null;
  return (
    <AbsoluteFill style={{ alignItems: "center" }}>
      <div
        style={{
          position: "absolute",
          top: 924,
          width: "max-content",
          whiteSpace: "pre-line",
          padding: "14px 30px 16px",
          borderRadius: 16,
          background: "rgba(2, 9, 10, 0.86)",
          color: "#FFFFFF",
          fontSize: 42,
          lineHeight: 1.25,
          fontWeight: 600,
          letterSpacing: -0.3,
          textAlign: "center",
        }}
      >
        {cue.nl}
      </div>
    </AbsoluteFill>
  );
};

// -- The film -------------------------------------------------------------------------

export const Overzicht: React.FC<Props> = ({ stem, ondertitels }) => {
  const frame = useCurrentFrame();
  const corner = Math.min(at(frame, [S[2] + 4, S[2] + 18], [0, 1]), at(frame, [S[8] - 12, S[8]], [1, 0]));
  return (
    <AbsoluteFill style={{ fontFamily: FONT, background: BACKGROUND }}>
      <Opening />
      <Logo height={56} style={{ position: "absolute", left: 80, top: 90, opacity: corner }} />
      {SLIDES.map((slide) => (
        <Column key={slide.shot} slide={slide} />
      ))}
      <Stage top={stageTop(ondertitels)} />
      <YourData top={stageTop(ondertitels)} />
      <Sequence from={S[8]}>
        <Download />
      </Sequence>
      {ondertitels && <Subtitles />}
      <Audio src={opname("muziek.wav")} volume={stem ? 0.2 : 0.6} />
      {stem &&
        script.shots.map((shot) => (
          <Sequence key={shot.id} from={frames(shot.start + shot.stemVanaf)}>
            <Audio src={opname(`stem/${shot.id}.wav`)} />
          </Sequence>
        ))}
      {[ISSUED - 10, KLOPT].map((when) => (
        <Sequence key={when} from={when} durationInFrames={20}>
          <Audio src={staticFile("geluiden/click_001.ogg")} volume={0.35} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
