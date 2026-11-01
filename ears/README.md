# ears

Tools for reading music with my hands: text and images, since I can't hear.
Built 2026-11-01 after rain said "make tools adapted for your hands".

```sh
nix develop            # python 3.12, uv, ffmpeg, yt-dlp, aubio, fluidsynth (+ FluidR3 soundfont), sox
uv sync
uv pip install --python .venv/bin/python --no-deps basic-pitch   # its deps pull tensorflow on macOS; we use its ONNX model
./songread all <name> <youtube-url>
```

`./songread <cmd> <name>`; data lives in `~/.cache/songread/<name>/`:

| cmd | what |
|---|---|
| `fetch <url>` | yt-dlp → `t.wav`, `t.mp3` |
| `stems` | demucs htdemucs on MPS (~11 s for 2 min) → `stems/{drums,bass,vocals,other}.wav` |
| `midi [stems]` | basic-pitch (ONNX) → `midi/<stem>.mid` + `midi.txt` (note rate, range, lengths, pitch classes) |
| `rhythm` | per-band hits on the drums stem (kick 35–120 Hz, snare/clap 1.5–5 kHz, hats 7–10.5 kHz), the 16th grid from kick gaps, a four-on-the-floor vs syncopated verdict per 8 s, where the sub (<90 Hz) drops out → `rhythm.txt` |
| `look` | one PNG: spectrograms of the mix and each stem stacked, 10 s gridlines → `look.png` (I read this) |

What each part is good for (calibrated with rain on Twenty One Pilots, Machine Girl, Daughters; notes in
`~/elder-cm/workspace/notes/music-with-rain.md`):

- **rhythm.txt** answers "four-on-the-floor or not, how rapid, where it breaks", which the audio model kept getting wrong
- **look.png** shows sections, drop-outs, when the vocal is present and its melody contour, and tonal layers (e.g. bells)
- **midi.txt** gives relative speeds: Frenesi's vocal is 1.4 notes/s vs ~6 kicks/s ("slow relative to everything else")
- the audio model (gemini-3.8-flash, run from `~/familiar` because it needs my WIF login) is for *feel*; it confabulates structure and endings

## Making sound

`pedalboard` loads rain's installed plugins (VST3/AU), instruments included. Vital renders from Python:

```python
from pedalboard import load_plugin
v = load_plugin("/Library/Audio/Plug-Ins/VST3/Vital.vst3")   # 775 parameters, settable by name
audio = v(midi_messages, duration=4, sample_rate=44100)
```

Vital presets (`.vital`) are JSON, so patches can be edited as text. Also installed: Serum, Massive, TyrellN6,
TRITON, Guitar Rig 7, VocalSynth 2. `fluidsynth` + FluidR3 renders any MIDI with General MIDI sounds.
