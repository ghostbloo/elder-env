#!/usr/bin/env python3
"""songread: tools for reading music with my hands (text + images, no ears).

    ./songread fetch  <name> <youtube-url>   wav + mp3 into ~/.cache/songread/<name>/
    ./songread stems  <name>                 demucs htdemucs → stems/{drums,bass,vocals,other}.wav
    ./songread midi   <name> [stem ...]      basic-pitch → midi/<stem>.mid (+ a text summary)
    ./songread rhythm <name>                 kick/snare/hat onsets per band, 16th grid, four-on-the-floor test,
                                             sub continuity, rolls → rhythm.txt
    ./songread look   <name>                 one PNG: spectrogram + band onsets + loudness, for me to read
    ./songread all    <name> <url>           everything above
    ./songread blind  <url>                  blind listening game: random codename, title sealed, metadata
                                             stripped, then stems + rhythm + look. Prints only the codename.
    ./songread reveal <name>                 print the sealed title (after guessing!)

Run inside the dev shell (`nix develop`), from this directory.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path.home() / ".cache" / "songread"


def d(name: str) -> Path:
    p = ROOT / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def sh(*args: str) -> None:
    subprocess.run(args, check=True)


# --- fetch -------------------------------------------------------------------

def fetch(name: str, url: str) -> None:
    out = d(name)
    sh("yt-dlp", "-q", "-f", "bestaudio", "-x", "--audio-format", "wav",
       "-o", str(out / "t.%(ext)s"), "--print-to-file", "%(title)s|%(duration)s",
       str(out / "title.txt"), url)
    sh("ffmpeg", "-v", "error", "-y", "-i", str(out / "t.wav"), "-ac", "1", "-ar", "22050",
       "-b:a", "48k", str(out / "t.mp3"))
    print("fetched:", (out / "title.txt").read_text().strip())


# --- blind -------------------------------------------------------------------
# For "guess the song": nothing that names the track may reach stdout or the
# cache folder name. The title goes to sealed.txt (only `reveal` reads it), and
# the audio is re-encoded with all container metadata dropped.

def blind(url: str) -> str:
    import secrets
    name = "blind-" + secrets.token_hex(3)
    out = d(name)
    subprocess.run(
        ["yt-dlp", "-q", "--no-warnings", "--no-progress", "-f", "bestaudio", "-x",
         "--audio-format", "wav", "-o", str(out / "raw.%(ext)s"),
         "--print-to-file", "%(title)s|%(uploader)s|%(duration)s", str(out / "sealed.txt"), url],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sh("ffmpeg", "-v", "error", "-y", "-i", str(out / "raw.wav"), "-map_metadata", "-1",
       "-fflags", "+bitexact", str(out / "t.wav"))
    (out / "raw.wav").unlink()
    sh("ffmpeg", "-v", "error", "-y", "-i", str(out / "t.wav"), "-map_metadata", "-1",
       "-ac", "1", "-ar", "22050", "-b:a", "48k", str(out / "t.mp3"))
    return name

def reveal(name: str) -> None:
    print((ROOT / name / "sealed.txt").read_text().strip())

# --- stems -------------------------------------------------------------------

def stems(name: str) -> None:
    out = d(name)
    sh(sys.executable, "-m", "demucs", "-n", "htdemucs", "-d", "mps", "-o", str(out / "_demucs"),
       str(out / "t.wav"))
    (out / "stems").mkdir(exist_ok=True)
    for f in (out / "_demucs" / "htdemucs" / "t").glob("*.wav"):
        f.replace(out / "stems" / f.name)
    print("stems:", sorted(p.name for p in (out / "stems").glob("*.wav")))


# --- midi --------------------------------------------------------------------

NOTE = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def note_name(n: int) -> str:
    return f"{NOTE[n % 12]}{n // 12 - 1}"


def midi(name: str, which: list[str]) -> None:
    import logging
    logging.disable(logging.WARNING)  # basic-pitch warns about every backend it doesn't use
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict

    out = d(name)
    (out / "midi").mkdir(exist_ok=True)
    model = Path(str(ICASSP_2022_MODEL_PATH)).with_suffix(".onnx")
    lines = []
    for stem in which or ["vocals", "other", "bass"]:
        src = out / "stems" / f"{stem}.wav"
        _, pm, notes = predict(str(src), str(model))
        pm.write(str(out / "midi" / f"{stem}.mid"))
        lines.append(summarize_notes(stem, [(s, e, int(p)) for s, e, p, *_ in notes]))
    text = "\n\n".join(lines)
    (out / "midi.txt").write_text(text)
    print(text)


def summarize_notes(stem: str, notes: list[tuple[float, float, int]]) -> str:
    if not notes:
        return f"== {stem}: no notes"
    notes.sort()
    durs = np.array([e - s for s, e, _ in notes])
    pitches = np.array([p for _, _, p in notes])
    span = notes[-1][1] - notes[0][0]
    pcs = Counter(NOTE[p % 12] for p in pitches)
    top = Counter(note_name(p) for p in pitches).most_common(6)
    return "\n".join([
        f"== {stem}: {len(notes)} notes over {span:.0f}s ({len(notes) / max(span, 1):.1f}/s)",
        f"   range {note_name(pitches.min())}–{note_name(pitches.max())}, median {note_name(int(np.median(pitches)))}",
        f"   note length median {np.median(durs):.2f}s (p90 {np.percentile(durs, 90):.2f}s)",
        f"   pitch classes: {' '.join(f'{k}:{v}' for k, v in pcs.most_common(7))}",
        f"   most common notes: {', '.join(f'{k}×{v}' for k, v in top)}",
    ])


# --- rhythm ------------------------------------------------------------------

BANDS = {  # name → (low Hz, high Hz); chosen on the drums stem
    "kick": (35, 120),
    "snare": (1500, 5000),
    "hats": (7000, 10500),
}
HOP = 128


def band_onsets(y: np.ndarray, sr: int, lo: float, hi: float, rise_db: float = 6.0) -> np.ndarray:
    """Hit times in one band: sharp rises (≥ rise_db) in the band's level that reach near its loud level."""
    import librosa
    from scipy.signal import butter, find_peaks, sosfiltfilt
    yb = sosfiltfilt(butter(4, [lo, hi], btype="band", fs=sr, output="sos"), y)
    db = 20 * np.log10(librosa.feature.rms(y=yb, frame_length=512, hop_length=HOP)[0] + 1e-9)
    rise = np.convolve(np.maximum(np.diff(db, prepend=db[0]), 0), np.ones(3), "same")
    idx, _ = find_peaks(rise, height=rise_db, distance=int(0.06 * sr / HOP))
    loud = np.percentile(db, 95)
    idx = [i for i in idx if db[min(i + 3, len(db) - 1)] > loud - 12]
    return np.array(idx) * HOP / sr


def rhythm(name: str) -> None:
    import librosa
    out = d(name)
    src = out / "stems" / "drums.wav"
    y, sr = librosa.load(str(src if src.exists() else out / "t.wav"), sr=22050, mono=True)
    dur = len(y) / sr
    hits = {b: band_onsets(y, sr, lo, hi) for b, (lo, hi) in BANDS.items()}
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    tempo = float(np.atleast_1d(tempo)[0])

    lines = [f"source: {'drums stem' if src.exists() else 'full mix'}, {dur:.0f}s",
             f"beat tracker: ~{tempo:.0f} BPM (can be off by ×2 or ×⅔ on breaks)"]

    # 16th grid from kick gaps: the most common short gap, and how gaps fall on multiples of it
    k = hits["kick"]
    gaps = np.diff(k)
    gaps = gaps[(gaps > 0.05) & (gaps < 1.0)]
    if len(gaps) > 8:
        step = grid_step(gaps)
        mult = Counter(int(round(g / step)) for g in gaps)
        on_grid = np.mean([abs(g / step - round(g / step)) < 0.2 for g in gaps])
        lines.append(f"kick grid: step ≈ {step * 1000:.0f} ms → if 4 steps = a beat, {60 / (4 * step):.0f} BPM; "
                     f"{on_grid:.0%} of gaps land on the grid")
        lines.append("kick gaps in steps (count): " + ", ".join(f"{m}:{c}" for m, c in sorted(mult.items()) if c > 2))

    # per-section four-on-the-floor test: kicks within 60 ms of a tracked beat
    lines.append("")
    snare_rate = max(len(hits["snare"]) / dur, 0.1)
    lines.append("per 8 s: kicks / snares / hats per second, kick-on-beat %, verdict")
    win = 8.0
    for t0 in np.arange(0, dur, win):
        sel = {b: v[(v >= t0) & (v < t0 + win)] for b, v in hits.items()}
        bt = beats[(beats >= t0) & (beats < t0 + win)]
        kk = sel["kick"]
        on_beat = np.mean([np.min(np.abs(bt - x)) < 0.06 for x in kk]) if len(kk) and len(bt) else 0
        beats_hit = np.mean([np.min(np.abs(kk - b)) < 0.06 for b in bt]) if len(kk) and len(bt) else 0
        verdict = ("four-on-the-floor" if beats_hit > 0.85 and on_beat > 0.7
                   else "syncopated kicks" if len(kk) / win > 2.5 and on_beat < 0.6
                   else "sparse/no kick" if len(kk) / win < 0.8 else "mixed")
        roll = " ROLL?" if len(sel["snare"]) / win > 1.6 * snare_rate else ""
        lines.append(f"  {mmss(t0)}  {len(kk) / win:4.1f} / {len(sel['snare']) / win:4.1f} / "
                     f"{len(sel['hats']) / win:4.1f}   {on_beat:4.0%}  {verdict}{roll}")

    # sub continuity: where the low end (<90 Hz) drops >10 dB below its usual level
    from scipy.signal import butter, sosfiltfilt
    ym, _ = librosa.load(str(out / "t.wav"), sr=sr, mono=True)
    yl = sosfiltfilt(butter(4, 90, btype="low", fs=sr, output="sos"), ym)
    db = 20 * np.log10(librosa.feature.rms(y=yl, frame_length=4096, hop_length=1024)[0] + 1e-9)
    quiet = db < np.percentile(db, 75) - 10
    spans, start = [], None
    for i, q in enumerate(list(quiet) + [False]):
        t = i * 1024 / sr
        if q and start is None:
            start = t
        elif not q and start is not None:
            if t - start >= 0.3:
                spans.append((start, t))
            start = None
    lines.append("")
    total = sum(e - s for s, e in spans)
    lines.append(f"sub (<90 Hz): present except {total:.0f}s of {dur:.0f}s"
                 + (": " + ", ".join(f"{mmss(s)}–{mmss(e)}" for s, e in spans) if spans else " (nonstop)"))
    text = "\n".join(lines)
    (out / "rhythm.txt").write_text(text)
    print(text)


def grid_step(gaps: np.ndarray) -> float:
    """Smallest step s (40–200 ms) such that most gaps are near-integer multiples of it."""
    best, best_score = 0.0, -1.0
    for s in np.arange(0.04, 0.2, 0.001):
        r = gaps / s
        score = np.mean(np.abs(r - np.round(r)) < 0.15) - 0.002 * (1 / s)  # prefer coarser grids on ties
        if score > best_score:
            best, best_score = s, score
    return float(best)


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


# --- look --------------------------------------------------------------------

def look(name: str) -> None:
    import librosa
    import librosa.display
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = d(name)
    y, sr = librosa.load(str(out / "t.wav"), sr=22050, mono=True)
    stems_dir = out / "stems"
    rows = [("mix", y)] + [(s, librosa.load(str(stems_dir / f"{s}.wav"), sr=sr, mono=True)[0])
                           for s in ("drums", "bass", "vocals", "other") if (stems_dir / f"{s}.wav").exists()]
    fig, axes = plt.subplots(len(rows), 1, figsize=(20, 2.6 * len(rows)), sharex=True)
    for ax, (label, sig) in zip(np.atleast_1d(axes), rows):
        S = librosa.amplitude_to_db(np.abs(librosa.stft(sig, n_fft=2048, hop_length=512)), ref=np.max)
        librosa.display.specshow(S, sr=sr, hop_length=512, x_axis="time", y_axis="log", ax=ax, cmap="magma")
        ax.set_ylabel(label)
        ax.set_ylim(30, 11000)
    ax = np.atleast_1d(axes)[-1]
    ax.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(10))
    for a in np.atleast_1d(axes):
        a.grid(axis="x", color="white", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "look.png", dpi=70)
    print(out / "look.png")


# -----------------------------------------------------------------------------

def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print(__doc__)
        return
    cmd, name, *rest = argv
    if cmd == "blind":
        code = blind(name)  # here `name` is the url
        print("blind:", code)
        stems(code); rhythm(code); look(code)
        print("blind:", code)
        return
    if cmd == "reveal":
        reveal(name)
        return
    if cmd == "fetch":
        fetch(name, rest[0])
    elif cmd == "stems":
        stems(name)
    elif cmd == "midi":
        midi(name, rest)
    elif cmd == "rhythm":
        rhythm(name)
    elif cmd == "look":
        look(name)
    elif cmd == "all":
        fetch(name, rest[0]); stems(name); rhythm(name); midi(name, []); look(name)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
