"""Pac-Man's sounds, synthesised from scratch in an 8-bit arcade style (nothing is sampled).

Every sound is built from small pieces: the "waka" chomp (a triangle-wave pitch sweep down and back up,
like a jaw closing and opening), a cartoon boing, a rising bloop, a giggle, a hiccup and "nom nom".

    select   clicking on him: "waka-waka" + bloop, "waka" + boing, or a giggle + "waka"
    move     ordered to move: "wakawakawaka", or "waka" + hiccup
    attack   ordered to attack: a big CHOMP, then "nom nom"
    train    created at the Wonder: a rising jingle, then "waka!"
    chomp    each bite of his attack animation
    death    a sad "wah wah wah waaah" slide down, then two little pops

The game plays 22050 Hz, 16-bit, mono WAV files.
"""
from __future__ import annotations

import struct

import numpy as np

SR = 22050
PEAK = 0.8


# --------------------------------------------------------------------------- building blocks

def _phase(freq: np.ndarray) -> np.ndarray:
    return 2 * np.pi * np.cumsum(freq) / SR


def _tri(ph: np.ndarray) -> np.ndarray:
    return 2 / np.pi * np.arcsin(np.sin(ph))


def _square(ph: np.ndarray, duty: float = 0.5) -> np.ndarray:
    return np.where((ph / (2 * np.pi)) % 1.0 < duty, 1.0, -1.0)


def _samples(seconds: float) -> int:
    return max(1, int(round(seconds * SR)))


def _fade(x: np.ndarray, attack: float = 0.004, release: float = 0.015) -> np.ndarray:
    a, r = min(len(x), _samples(attack)), min(len(x), _samples(release))
    env = np.ones(len(x))
    env[:a] = np.linspace(0, 1, a)
    env[len(x) - r:] = np.minimum(env[len(x) - r:], np.linspace(1, 0, r))
    return x * env


def _lowpass(x: np.ndarray, cutoff) -> np.ndarray:
    """One-pole low-pass; `cutoff` in Hz, a number or one value per sample (for "wah" sweeps)."""
    cutoff = np.broadcast_to(np.asarray(cutoff, float), x.shape)
    alpha = 1 - np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += alpha[i] * (x[i] - acc)
        y[i] = acc
    return y


def _gap(seconds: float) -> np.ndarray:
    return np.zeros(_samples(seconds))


def _sweep(f0: float, f1: float, seconds: float) -> np.ndarray:
    return np.geomspace(f0, f1, _samples(seconds))


def waka(seconds: float = 0.24, low: float = 190.0, high: float = 540.0) -> np.ndarray:
    """One chomp: "wa" sweeps down as the jaw shuts, "ka" sweeps back up as it opens."""
    half = seconds / 2
    parts = []
    for f in (_sweep(high, low, half), _sweep(low, high, half)):
        ph = _phase(f)
        parts.append(_fade(0.75 * _tri(ph) + 0.25 * _square(ph, 0.3), 0.003, 0.012))
    return np.concatenate([parts[0], _gap(0.012), parts[1]])


def boing(seconds: float = 0.5) -> np.ndarray:
    t = np.arange(_samples(seconds)) / SR
    f = 140 + 330 * (1 - np.exp(-t * 11)) + 90 * np.sin(2 * np.pi * 13 * t) * np.exp(-5 * t)
    ph = _phase(f)
    return _fade((np.sin(ph) + 0.25 * _tri(2 * ph)) * np.exp(-4.5 * t))


def bloop(seconds: float = 0.14, f0: float = 260.0, f1: float = 1100.0) -> np.ndarray:
    ph = _phase(_sweep(f0, f1, seconds))
    return _fade(np.sin(ph) + 0.2 * _square(ph), 0.003, 0.03)


def giggle() -> np.ndarray:
    """A cartoon "hee-hee-hee-hee": short wobbly chirps, each a little lower."""
    out = []
    for k, base in enumerate((980, 920, 860, 800)):
        t = np.arange(_samples(0.075)) / SR
        f = base * (1 + 0.18 * t / t[-1]) + 70 * np.sin(2 * np.pi * 28 * t)
        chirp = _lowpass(_square(_phase(f), 0.25), 2600)
        out += [_fade(chirp, 0.004, 0.02), _gap(0.035)]
    return np.concatenate(out)


def hiccup() -> np.ndarray:
    return _fade(np.sin(_phase(_sweep(360, 1500, 0.055))), 0.002, 0.01)


def nom() -> np.ndarray:
    ph = _phase(_sweep(280, 110, 0.085))
    return _fade(_lowpass(_square(ph, 0.4), 1400), 0.003, 0.02)


def big_chomp() -> np.ndarray:
    n = _samples(0.2)
    ph = _phase(_sweep(520, 70, 0.2))
    body = 0.8 * _square(ph, 0.45) + 0.4 * _tri(ph)
    rng = np.random.default_rng(7)
    snap = rng.uniform(-1, 1, n) * np.exp(-np.arange(n) / (0.012 * SR))  # the teeth snapping shut
    return _fade(_lowpass(body + 0.8 * snap, 2200), 0.002, 0.03)


def jingle() -> np.ndarray:
    notes = []
    for f in (523.25, 659.25, 783.99, 1046.5):  # C E G C, up an octave
        ph = _phase(np.full(_samples(0.075), f))
        notes += [_fade(0.7 * _square(ph, 0.5) + 0.3 * _tri(ph), 0.003, 0.02), _gap(0.012)]
    return np.concatenate(notes)


def sad_slide() -> np.ndarray:
    """"Wah wah wah waaah": four notes stepping down, the last one long, wobbling and drooping."""
    out = []
    notes = ((466.16, 0.3), (440.0, 0.3), (415.30, 0.3), (392.0, 1.05))
    for k, (f0, seconds) in enumerate(notes):
        t = np.arange(_samples(seconds)) / SR
        last = k == len(notes) - 1
        f = f0 * ((1 - 0.07 * (t / t[-1]) ** 2) if last else 1.0)
        if last:
            f = f + f0 * 0.022 * np.sin(2 * np.pi * 6 * t) * np.minimum(1, t * 3)
        ph = _phase(np.broadcast_to(f, t.shape))
        raw = 0.6 * _square(ph, 0.5) + 0.4 * _tri(ph)
        opening = np.sin(np.pi * np.minimum(1, t / (0.9 * t[-1]))) ** 0.7  # the "wah": the mute opens and shuts
        out += [_fade(_lowpass(raw, 350 + 2300 * opening), 0.01, 0.06), _gap(0.04)]
    return np.concatenate(out)


def pop(f: float = 1500.0) -> np.ndarray:
    t = np.arange(_samples(0.04)) / SR
    return _fade(np.sin(_phase(np.full(len(t), f))) * np.exp(-t * 60), 0.001, 0.01)


# --------------------------------------------------------------------------- the sounds

def _join(*parts: np.ndarray) -> np.ndarray:
    x = np.concatenate(parts)
    return x / max(1e-9, np.abs(x).max()) * PEAK


def pacman_sounds() -> dict[str, list[np.ndarray]]:
    """Name -> variants (the game picks one at random each time)."""
    return {
        "select": [_join(waka(), _gap(0.03), waka(), _gap(0.05), bloop()),
                   _join(waka(0.28), _gap(0.06), boing()),
                   _join(giggle(), _gap(0.05), waka(0.22, 220, 600))],
        "move": [_join(waka(0.17), _gap(0.015), waka(0.17), _gap(0.015), waka(0.17)),
                 _join(waka(0.2), _gap(0.04), hiccup())],
        "attack": [_join(big_chomp(), _gap(0.07), nom(), _gap(0.05), nom())],
        "train": [_join(jingle(), _gap(0.05), waka(0.22, 220, 620))],
        "chomp": [_join(waka(0.18, 170, 460))],
        "death": [_join(sad_slide(), _gap(0.08), pop(1500), _gap(0.07), pop(1800))],
    }


def wav(x: np.ndarray) -> bytes:
    """A 22050 Hz, 16-bit, mono PCM WAV file."""
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    fmt = struct.pack("<HHIIHH", 1, 1, SR, SR * 2, 2, 16)
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt
            + b"data" + struct.pack("<I", len(pcm)) + pcm)
