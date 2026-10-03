"""The Dragon's sounds, synthesised from scratch (nothing is sampled): deep, rough and echoing, like Minecraft's
Ender Dragon.

A roar is a voice. Its throat buzzes low (a sawtooth, plus one an octave below for the doubled, rough beat of a
growl), chopped into a rattle 20-30 times a second, with breath through it. Its mouth is a set of formants (the
resonances that make vowels) that open from "oo" to "aah" and back, pitched for a throat about twice as long as a
person's. Then it is overdriven for grit and echoes a little, as if among hills. Wing beats are a rush of air and a
deep whump; fire is noise opening up like a gas burner, with a rumble and crackles.

    select   clicking on it: a low growl, a snort and a purr, or a rumbling "hrrm?"
    move     ordered to move: two beats of its wings, or a huff and a wing beat
    attack   ordered to attack: a roar, or a snarl rising into a roar
    train    created at the Wonder: a long roar, then its wings beating as it takes off
    fire     each fireball it spits: a "fwoosh" of flame with crackles
    death    a roar falling away as it drops, the thud as it hits the ground, a last groan

The game plays 22050 Hz, 16-bit, mono WAV files (sounds.wav writes them).
"""
from __future__ import annotations

import zlib
from functools import lru_cache

import numpy as np

from .sounds import PEAK, SR

_WINDOW, _HOP, _FFT = 1024, 256, 2048  # the slices _filter works on: 46 ms, a new one every 12 ms

# its mouth: formants (Hz) shut ("oo") and wide open ("aah"), a person's at about half the pitch, and how wide and
# loud each is
SHUT = (170, 450, 1250, 1900)
OPEN = (420, 640, 1350, 2100)
WIDTHS = (110, 150, 220, 300)
LEVELS = (1.0, 0.8, 0.45, 0.3)


# --------------------------------------------------------------------------- building blocks

def _rng(name: str) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(name.encode()))


def _time(seconds: float) -> np.ndarray:
    return np.arange(max(1, int(round(seconds * SR)))) / SR


def _curve(t, points) -> np.ndarray:
    """Straight lines through (seconds, value) points, flat past the ends."""
    times, values = zip(*points)
    return np.interp(t, times, values)


def _wander(rng: np.random.Generator, n: int, rate: float) -> np.ndarray:
    """A smooth random wobble between -1 and 1, turning about `rate` times a second."""
    k = int(n / SR * rate) + 3
    pos = np.arange(n) * (k - 1) / max(1, n - 1)
    i = np.minimum(pos.astype(int), k - 2)
    w = (1 - np.cos(np.pi * (pos - i))) / 2
    points = rng.uniform(-1, 1, k)
    return points[i] * (1 - w) + points[i + 1] * w


def _filter(x: np.ndarray, gain) -> np.ndarray:
    """`x` through a filter that may change as it goes: gain(f, t) is how much of f Hz (a row) passes t seconds in
    (a column). Overlapping slices are filtered one by one and added back up."""
    n = len(x)
    lead = (_FFT - _WINDOW) // 2  # room on both sides of a slice for the filter's ringing
    starts = np.arange(-_WINDOW, n, _HOP)
    padded = np.concatenate([np.zeros(_WINDOW), x, np.zeros(_WINDOW)])
    slices = np.zeros((len(starts), _FFT))
    window = np.hanning(_WINDOW + 1)[:-1]
    slices[:, lead:lead + _WINDOW] = padded[starts[:, None] + _WINDOW + np.arange(_WINDOW)] * window
    f = np.fft.rfftfreq(_FFT, 1 / SR)[None, :]
    t = ((starts + _WINDOW / 2) / SR)[:, None]
    y = np.fft.irfft(np.fft.rfft(slices) * gain(f, t), _FFT)
    out = np.zeros(n + 3 * _FFT)
    for s, row in zip(starts, y):
        out[s - lead + _FFT:s - lead + 2 * _FFT] += row
    return out[_FFT:_FFT + n] / 2  # Hann windows a quarter of their length apart add up to 2


def _lowpass(cutoff: float, steep: int = 2):
    return lambda f, t: 1 / np.sqrt(1 + (f / cutoff) ** (2 * steep))


def _highpass(cutoff: float, steep: int = 1):
    return lambda f, t: 1 / np.sqrt(1 + (cutoff / np.maximum(f, 1e-3)) ** (2 * steep))


def _band(centre, width: float):
    """A bump around `centre` Hz (a number, or (seconds, Hz) points for one that slides)."""
    def gain(f, t):
        c = _curve(t, centre) if isinstance(centre, (list, tuple)) else centre
        return 1 / np.sqrt(1 + ((f - c) / (width / 2)) ** 2)
    return gain


def _norm(x: np.ndarray) -> np.ndarray:
    return x / max(1e-9, np.abs(x).max())


def _grit(x: np.ndarray, drive: float) -> np.ndarray:
    """Overdriven: the loud parts squashed flat, which roughens them."""
    return np.tanh(drive * _norm(x)) / np.tanh(drive)


def _noise(rng: np.random.Generator, t: np.ndarray) -> np.ndarray:
    return rng.standard_normal(len(t))


def _voice(rng: np.random.Generator, t: np.ndarray, pitch, rasp: float = 0.5, rasp_rate: float = 26.0,
           sub: float = 0.45, breath: float = 0.45, jitter: float = 0.06) -> np.ndarray:
    """The buzz of its throat at `pitch` Hz (per sample): a sawtooth and its octave below, unsteady in pitch and
    loudness as a beast's throat is, chopped into a rattle (`rasp`, 0 smooth to 1 fully chopped), with breath."""
    f0 = pitch * (1 + jitter * _wander(rng, len(t), 14) + 0.3 * jitter * _wander(rng, len(t), 60))
    cycles = np.cumsum(f0) / SR
    buzz = 2 * (cycles % 1) - 1 + sub * (2 * (cycles / 2 % 1) - 1)
    beat = np.cumsum(rasp_rate * (1 + 0.2 * _wander(rng, len(t), 4))) / SR
    chop = (0.5 + 0.5 * np.cos(2 * np.pi * beat)) ** 2
    shimmer = 1 + 0.25 * _wander(rng, len(t), 70)
    return buzz * (1 - rasp + rasp * chop) * shimmer + breath * _noise(rng, t)


def _mouth(opening):
    """What its mouth lets through, `opening` being (seconds, 0 shut to 1 wide open) points."""
    def gain(f, t):
        o = _curve(t, opening)
        g = 0.04
        for k, (shut, wide, width, level) in enumerate(zip(SHUT, OPEN, WIDTHS, LEVELS)):
            loud = level * (1 if k == 0 else 0.35 + 0.65 * o)  # an open mouth is brighter
            g = g + loud / np.sqrt(1 + ((f - (shut + (wide - shut) * o)) / (width / 2)) ** 2)
        return g * _highpass(40)(f, t)
    return gain


def _finish(x: np.ndarray) -> np.ndarray:
    """No hiss above 5 kHz (the overdrive makes some) and no rumble below hearing, which would only take up room."""
    return _filter(x, lambda f, t: _lowpass(5000)(f, t) * _highpass(50, 2)(f, t))


def _echo(x: np.ndarray, mix: float, seconds: float = 0.7) -> np.ndarray:
    """`x` and its echo: a burst of noise dying away, duller as it goes, mixed in at `mix`."""
    rng = _rng("echo")
    t = _time(seconds)
    tail = _filter(_noise(rng, t) * np.exp(-t / (seconds / 6)), _lowpass(2500, 1))
    tail[:int(0.015 * SR)] = 0  # it comes back a moment later
    tail /= np.sqrt((tail ** 2).sum())
    n = len(x) + len(t) - 1
    size = 1 << (n - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(tail, size), size)[:n]
    return np.concatenate([x, np.zeros(len(t) - 1)]) + mix * wet


def _mix(*placed: tuple[float, np.ndarray]) -> np.ndarray:
    """Sounds laid over each other, each (start in seconds, sound)."""
    out = np.zeros(max(int(round(s * SR)) + len(x) for s, x in placed))
    for s, x in placed:
        at = int(round(s * SR))
        out[at:at + len(x)] += x
    return out


def _env(t: np.ndarray, points) -> np.ndarray:
    return _curve(t, points) ** 1.5


# --------------------------------------------------------------------------- pieces

def roar(rng: np.random.Generator, seconds: float = 1.3, low: float = 55.0, high: float = 95.0,
         opening: float = 0.9, rasp: float = 0.45, falling: bool = False) -> np.ndarray:
    """Its mouth opening wide and shutting again, the pitch rising and falling (or only falling, from the start)."""
    t, s = _time(seconds), seconds
    rise = [(0, high), (0.15 * s, 1.05 * high)] if falling else [(0, 0.85 * low), (0.3 * s, high),
                                                                  (0.65 * s, 0.9 * high)]
    pitch = _curve(t, rise + [(s, low)])
    x = _filter(_voice(rng, t, pitch, rasp), _mouth([(0, 0.1), (0.25 * s, opening), (0.7 * s, 0.9 * opening),
                                                     (s, 0.15)]))
    return _grit(x, 3.0) * _env(t, [(0, 0), (min(0.15, 0.2 * s), 1), (0.7 * s, 0.85), (s, 0)])


def growl(rng: np.random.Generator, seconds: float = 0.8, pitch=55.0, opening=0.15, rasp_rate: float = 22.0,
          rasp: float = 0.75) -> np.ndarray:
    """A low rumble with its mouth (nearly) shut; `pitch` and `opening` may be (seconds, value) points."""
    t = _time(seconds)
    f0 = _curve(t, pitch) if isinstance(pitch, (list, tuple)) else np.full(len(t), pitch)
    shape = opening if isinstance(opening, (list, tuple)) else [(0, opening)]
    x = _filter(_voice(rng, t, f0, rasp, rasp_rate, breath=0.25), _mouth(shape))
    return _grit(x, 2.5) * _env(t, [(0, 0), (0.1, 1), (0.75 * seconds, 0.9), (seconds, 0)])


def snort(rng: np.random.Generator, seconds: float = 0.22) -> np.ndarray:
    """Air blown out through its nostrils, which flutter."""
    t = _time(seconds)
    nose = lambda f, tt: _band(1100, 1400)(f, tt) + 0.6 * _band(350, 300)(f, tt)
    x = _filter(_noise(rng, t), nose) * (1 + 0.5 * np.sin(2 * np.pi * 55 * t))
    return _norm(x) * np.minimum(1, t / 0.015) * np.exp(-t / 0.07)


def flap(rng: np.random.Generator, strength: float = 1.0) -> np.ndarray:
    """One beat of its wings: air rushing as they sweep down, then the deep whump of the air they push."""
    t, down = _time(0.55), 0.16  # the down stroke ends here
    rush = _filter(_noise(rng, t), _band([(0, 450), (down, 900), (0.55, 600)], 800))
    rush *= np.where(t < down, (t / down) ** 2, np.exp(-(t - down) / 0.04)) * (1 + 0.35 * np.sin(2 * np.pi * 34 * t))
    after = np.clip(t - down, 0, None)
    hit = np.where(t < down, 0, np.exp(-after / 0.07) * np.minimum(1, after / 0.006))
    whump = _filter(_noise(rng, t), lambda f, tt: _lowpass(260, 1)(f, tt) * _highpass(60)(f, tt)) * hit
    boom = np.sin(2 * np.pi * np.cumsum(65 + 45 * np.exp(-after * 20)) / SR) * hit
    return strength * _grit(0.45 * _norm(rush) + _norm(whump) + 0.5 * boom, 1.5)


def fire(rng: np.random.Generator, seconds: float = 0.9, ignite: float = 1.0) -> np.ndarray:
    """A "fwoosh": noise opening up bright and closing down dull, a deep rumble under it, crackles over it, and the
    thump of it catching (`ignite`)."""
    t = _time(seconds)
    cutoff = [(0, 300), (0.04, 3800), (0.2, 2600), (seconds, 600)]
    body = _filter(_noise(rng, t), lambda f, tt: _highpass(120)(f, tt) / np.sqrt(1 + (f / _curve(tt, cutoff)) ** 4))
    flicker = 1 + 0.25 * _wander(rng, len(t), 25)
    body *= np.minimum(1, t / 0.012) * _curve(t, [(0, 1), (0.25, 0.8), (seconds, 0)]) * flicker
    rumble = _filter(_noise(rng, t), _lowpass(120)) * _env(t, [(0, 0), (0.03, 1), (0.4 * seconds, 0.7), (seconds, 0)])
    pops = (rng.random(len(t)) < 45 / SR) * rng.uniform(0.3, 1, len(t))  # 45 crackles a second
    crackle = _filter(pops, _highpass(2000, 2)) * _curve(t, [(0, 0), (0.08, 1), (seconds, 0.2)])
    thump = np.sin(2 * np.pi * np.cumsum(60 + 40 * np.exp(-t * 18)) / SR) * np.exp(-t * 14) * np.minimum(1, t / 0.004)
    return _grit(_norm(body) + 0.7 * _norm(rumble) + 0.4 * _norm(crackle) + 0.6 * ignite * thump, 1.5)


def thud(rng: np.random.Generator) -> np.ndarray:
    """Something huge hitting the ground: a deep boom and a burst of earth."""
    t = _time(0.6)
    boom = np.sin(2 * np.pi * np.cumsum(55 + 60 * np.exp(-t * 16)) / SR) * np.exp(-t * 7) * np.minimum(1, t / 0.003)
    earth = _filter(_noise(rng, t), _lowpass(500)) * np.exp(-t * 22)
    return _grit(boom + 0.7 * _norm(earth), 2.0)


# --------------------------------------------------------------------------- the sounds

def _join(*placed: tuple[float, np.ndarray], echo: float = 0.25) -> np.ndarray:
    x = _echo(_finish(_mix(*placed)), echo)
    return x / max(1e-9, np.abs(x).max()) * PEAK


@lru_cache(maxsize=None)
def dragon_sounds(fall: float = 0.8) -> dict[str, list[np.ndarray]]:
    """Name -> variants (the game picks one at random each time). `fall`: seconds from the start of its dying
    animation until it hits the ground."""
    r = _rng
    return {
        "select": [_join((0, growl(r("growl"), 0.85))),
                   _join((0, snort(r("snort"))), (0.24, growl(r("purr"), 0.6, 60.0, 0.1, 17.0, 0.6))),
                   _join((0, growl(r("hrrm"), 0.75, [(0, 52), (0.45, 55), (0.75, 80)], [(0, 0.05), (0.75, 0.5)])))],
        "move": [_join((0, flap(r("flap1"))), (0.38, flap(r("flap2"), 0.85)), echo=0.15),
                 _join((0, snort(r("huff"), 0.26)), (0.2, flap(r("flap3"))), echo=0.15)],
        "attack": [_join((0, roar(r("roar1"), 1.0, 60.0, 105.0, 0.95))),
                   _join((0, growl(r("snarl"), 0.4, [(0, 50), (0.4, 75)], [(0, 0.1), (0.4, 0.5)], 28.0)),
                         (0.3, roar(r("roar2"), 0.85, 70.0, 110.0, 1.0)))],
        "train": [_join((0, roar(r("roar3"), 1.5, 50.0, 90.0, 1.0, 0.5)),
                        (1.25, flap(r("flap4"))), (1.63, flap(r("flap5"), 0.8)))],
        "fire": [_join((0, fire(r("fire1"))), echo=0.15),
                 _join((0, fire(r("fire2"), 0.75, 0.6)), echo=0.15)],
        "death": [_join((0, roar(r("cry"), fall + 0.2, 45.0, 105.0, 1.0, 0.6, falling=True)),
                        (fall, thud(r("thud"))),
                        (fall + 0.15, 0.45 * growl(r("groan"), 0.9, [(0, 50), (0.9, 38)], [(0, 0.3), (0.9, 0.05)])))],
    }
