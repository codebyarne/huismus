# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The sound of the overview film, run by scripts/promo-film.sh:

    promo_geluid.py <opname folder> <subtitles folder>

Reads the script (scripts/promo/film/src/overzicht.json: per shot when it
starts, how long it lasts and what is said) and makes, in the opname folder
Remotion reads (scripts/promo/film/public/opname/):

- stem/<shot>.wav: the voice, one file per shot. If
  scripts/promo/film/stem/<shot>.wav (or .mp3, .m4a, .aiff) exists, that
  recording is used; otherwise a trial voice speaks the line (macOS `say`,
  on this computer, nothing goes out). So the final voice replaces the
  trial one shot by shot, and the edit stays as it is.
- ondertitels.json: when each line shows, worked out from how long each
  shot's voice really lasts, so the subtitles follow another voice too.
- muziek.wav: a quiet track made here from sines (no licence to mind), or
  scripts/promo/film/muziek.<wav|mp3|m4a> if that exists.

And in the subtitles folder: huismus-overzicht.nl.vtt and .en.vtt.

A shot's voice must fit in its shot: if a recording is longer, this stops
and says by how much, instead of letting two lines run into each other.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

FILM = Path(__file__).resolve().parent / "promo" / "film"
SCRIPT = FILM / "src" / "overzicht.json"
RECORDINGS = FILM / "stem"
AUDIO = (".wav", ".mp3", ".m4a", ".aiff", ".aif")
RATE = 48_000
# Room between the end of a shot's voice and the next shot.
BREATH = 0.25


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
    )


def _seconds(path: Path) -> float:
    with wave.open(str(path)) as file:
        return file.getnframes() / file.getframerate()


def _recording(name: str) -> Path | None:
    """The owner's own file for a shot (or the music), if there is one."""
    return next((p for p in sorted(RECORDINGS.parent.glob(name)) if p.suffix in AUDIO), None)


def speak(shot: dict, trial: dict, out: Path) -> float:
    """stem/<shot>.wav, from the recording or the trial voice, every shot as
    loud as the others; returns how long it lasts."""
    wav = out / f"{shot['id']}.wav"
    source = _recording(f"stem/{shot['id']}.*")
    with tempfile.TemporaryDirectory() as work:
        if source is None:
            if not shutil.which("say"):
                sys.exit(
                    f"Geen opname voor {shot['id']} in {RECORDINGS}, en dit is geen Mac: "
                    "de proefstem komt van macOS (say)."
                )
            source = Path(work) / "proef.aiff"
            text = " ".join(line.get("zeg", line["nl"]) for line in shot["regels"])
            subprocess.run(
                ["say", "-v", trial["stem"], "-r", str(trial["tempo"]), "-o", str(source), text],
                check=True,
            )
        _ffmpeg(
            "-i", str(source),
            # Silence before and after goes: the script says when the voice starts.
            "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
            "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
            "loudnorm=I=-18:TP=-2:LRA=7",
            "-ar", str(RATE), "-ac", "1", str(wav),
        )  # fmt: skip
    return _seconds(wav)


def cues(shot: dict, voice: float) -> list[dict]:
    """When each line of a shot shows: the voice's time shared out by the
    length of what is said, each line staying until the next."""
    spoken = [len(line.get("zeg", line["nl"])) for line in shot["regels"]]
    start = shot["start"] + shot["stemVanaf"]
    out, at = [], start
    for line, length in zip(shot["regels"], spoken, strict=True):
        end = at + voice * length / sum(spoken)
        out.append({"van": round(at, 2), "tot": round(end, 2), "nl": line["nl"], "en": line["en"]})
        at = end
    # The last line stays until just before the next shot: time to read it.
    out[-1]["tot"] = round(shot["start"] + shot["duur"] - 0.3, 2)
    for line in out:
        line["nl"], line["en"] = _two_lines(line["nl"]), _two_lines(line["en"])
    return out


def _stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def _two_lines(text: str, width: int = 42) -> str:
    """A subtitle of at most two lines, broken at the space nearest the
    middle, and rather after a comma or a colon than inside a phrase."""
    if len(text) <= width:
        return text
    spaces = [i for i, c in enumerate(text) if c == " "]
    cut = min(spaces, key=lambda i: abs(i - len(text) / 2) - 9 * (text[i - 1] in ",:.?"))
    return text[:cut] + "\n" + text[cut + 1 :]


def vtt(lines: list[dict], language: str) -> str:
    blocks = [
        f"{n}\n{_stamp(line['van'])} --> {_stamp(line['tot'])}\n{line[language]}"
        for n, line in enumerate(lines, 1)
    ]
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"


# -- The music ---------------------------------------------------------------------

BEAT = 0.75  # 80 beats a minute
# Four bars that go round: Dmaj7, Bm7, Gmaj7, A6 (frequencies in Hz, low to high).
CHORDS = [
    [146.83, 185.00, 220.00, 277.18],
    [123.47, 146.83, 185.00, 220.00],
    [98.00, 123.47, 146.83, 185.00],
    [110.00, 138.59, 164.81, 185.00],
]
ARPEGGIO = [0, 1, 2, 3, 2, 1, 2, 3]  # which chord note each half beat plays


def _tone(freq: float, seconds: float, harmonics: tuple[float, ...]) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return sum(level * np.sin(2 * np.pi * freq * (n + 1) * t) for n, level in enumerate(harmonics))


def _add(track: np.ndarray, at: float, sound: np.ndarray, left: float, right: float) -> None:
    first = int(at * RATE)
    sound = sound[: max(len(track) - first, 0)]
    track[first : first + len(sound), 0] += left * sound
    track[first : first + len(sound), 1] += right * sound


def music(seconds: float, out: Path) -> None:
    """A calm bed under the voice: a soft pad per bar, a plucked arpeggio
    that comes in after the first bar, and a low note on beats one and three."""
    track = np.zeros((int(seconds * RATE), 2))
    bar = 4 * BEAT
    for number in range(int(seconds / bar) + 1):
        chord, start = CHORDS[number % len(CHORDS)], number * bar
        for note, freq in enumerate(chord):
            # Each note twice, a little apart in pitch and in place: it shimmers.
            for detune, left, right in ((0.997, 0.8, 0.4), (1.003, 0.4, 0.8)):
                pad = _tone(freq * detune, bar + 1.2, (1, 0.25, 0.08))
                t = np.arange(len(pad)) / RATE
                pad *= np.minimum(t / 0.9, 1) * np.minimum((bar + 1.2 - t) / 1.2, 1)
                _add(track, start, pad, 0.045 * left, 0.045 * right)
            del note
        for beat in (0, 2):
            bass = _tone(chord[0] / 2, 1.4, (1, 0.3))
            t = np.arange(len(bass)) / RATE
            bass *= np.minimum(t / 0.01, 1) * np.exp(-t / 0.55)
            _add(track, start + beat * BEAT, bass, 0.2, 0.2)
        if number == 0:
            continue
        for step, note in enumerate(ARPEGGIO):
            pluck = _tone(chord[note] * 2, 1.0, (1, 0.35, 0.12))
            t = np.arange(len(pluck)) / RATE
            pluck *= np.minimum(t / 0.004, 1) * np.exp(-t / 0.22)
            side = 0.75 if step % 2 else 0.35
            _add(track, start + step * BEAT / 2, pluck, 0.11 * side, 0.11 * (1.1 - side))
    t = np.arange(len(track)) / RATE
    fade = np.minimum(t / 0.6, 1) * np.minimum((seconds - t) / 3.5, 1)
    track *= fade[:, None]
    track *= 0.7 / np.abs(track).max()
    with wave.open(str(out), "wb") as file:
        file.setnchannels(2)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes((track * 32767).astype("<i2").tobytes())


def main(opname: Path, subtitles: Path) -> None:
    script = json.loads(SCRIPT.read_text())
    voices = opname / "stem"
    voices.mkdir(parents=True, exist_ok=True)
    subtitles.mkdir(parents=True, exist_ok=True)
    lines, too_long = [], []
    for shot in script["shots"]:
        voice = speak(shot, script["proefstem"], voices)
        room = shot["duur"] - shot["stemVanaf"] - BREATH
        if voice > room:
            too_long.append(f"{shot['id']}: de stem duurt {voice:.1f} s, er is {room:.1f} s")
        lines += cues(shot, voice)
        print(f"{shot['id']}: {voice:.1f} s stem in {shot['duur']} s", flush=True)
    if too_long:
        sys.exit(
            "De stem past niet in het shot. Maak de opname korter of het shot langer "
            f"({SCRIPT.name}):\n" + "\n".join(too_long)
        )
    (opname / "ondertitels.json").write_text(json.dumps(lines, indent=2, ensure_ascii=False))
    for language in ("nl", "en"):
        (subtitles / f"huismus-overzicht.{language}.vtt").write_text(vtt(lines, language))
    last = script["shots"][-1]
    seconds = last["start"] + last["duur"]
    own = _recording("muziek.*")
    if own:
        _ffmpeg("-i", str(own), "-t", str(seconds), "-ar", str(RATE), str(opname / "muziek.wav"))
    else:
        music(seconds, opname / "muziek.wav")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("promo_geluid.py <opname-map> <map voor de ondertitels>")
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
