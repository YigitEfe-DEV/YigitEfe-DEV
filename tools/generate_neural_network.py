#!/usr/bin/env python3
"""Generate the animated neural-network asset used in the GitHub profile README.

Outputs
-------
assets/neural-network.svg   self-contained CSS-animated SVG (primary asset)
assets/neural-network.gif   animated GIF fallback (optional, requires Pillow)

Both artefacts are rendered from the single geometry + timing model defined in
this file, so the animated SVG and the GIF show exactly the same picture.

The SVG is the asset that is actually referenced from README.md. GitHub renders
SVG referenced through ``<img>`` as an isolated image document: scripting is
disabled, but CSS animations and SMIL keep running, which is all this
visualisation needs. The GIF exists as a fallback for renderers that do not
animate SVG (plain terminals, chat clients, some markdown viewers).

Usage
-----
    python3 tools/generate_neural_network.py [--svg-only] [--gif-only]
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from string import Template
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------

BG = "#0D1117"          # main background
BG_SOFT = "#161B22"      # secondary background
WIRE = "#586575"        # connection lines
NODE_OFF = "#303D50"    # inactive neuron fill

INPUT_FILL = "#1F6FEB"  # input neurons
INPUT_GLOW = "#58A6FF"  # input glow
HIDDEN_FILL = "#388BFD" # hidden neurons
HIDDEN_GLOW = "#58A6FF" # hidden glow
SIGNAL = "#58A6FF"      # signal particles
OUTPUT_FILL = "#238636" # output neurons
OUTPUT_GLOW = "#3FB950" # output glow

LAYER_FILL = (INPUT_FILL, HIDDEN_FILL, HIDDEN_FILL, OUTPUT_FILL)
LAYER_GLOW = (INPUT_GLOW, HIDDEN_GLOW, HIDDEN_GLOW, OUTPUT_GLOW)
# Signal colour per layer transition; the final hop arrives in green.
EDGE_SIGNAL = (SIGNAL, SIGNAL, OUTPUT_GLOW)

# --------------------------------------------------------------------------
# Geometry -- 4 -> 6 -> 6 -> 2 fully connected feed-forward network
# --------------------------------------------------------------------------

WIDTH, HEIGHT = 840, 460
LAYER_X = (78, 312, 546, 776)
LAYER_YS = (
    (113.0, 191.0, 269.0, 347.0),                 # 4 input neurons
    (75.0, 137.0, 199.0, 261.0, 323.0, 385.0),    # 6 hidden neurons
    (75.0, 137.0, 199.0, 261.0, 323.0, 385.0),    # 6 hidden neurons
    (180.0, 280.0),                               # 2 output neurons
)
NODE_RADIUS = (13.0, 13.0, 13.0, 15.0)
HALO_SCALE = 2.8
CORNER_RADIUS = 18

# --------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------

CYCLE = 4.8            # seconds per loop
LAYER_PULSE = (0.0, 1.15, 2.30, 3.45)  # when each layer lights up
FADE_IN = 0.08         # particle fade-in at the source
TRAVEL = 0.80          # particle flight time across one layer gap
FADE_OUT = 0.08        # particle fade-out at the target
LAUNCH_LAG = 0.04      # delay between a layer lighting and its signals leaving
SPREAD = 0.45          # spread of launches inside one layer gap
NODE_LEAD = 0.26       # node lights this long before the first signal lands
NODE_RISE = 0.052      # node activation ramp
NODE_FADE = 0.60       # node activation decay

CORE_DASH = 5.0        # core particle length, in pathLength units (0..100)
GLOW_DASH = 13.0       # glow tail length, in pathLength units
CORE_WIDTH = 2.0       # core particle stroke width
GLOW_WIDTH = 6.5       # outer glow band width
GLOW_INNER_WIDTH = 3.4  # inner glow band width
GLOW_ALPHA = 0.09      # outer glow band opacity
GLOW_INNER_ALPHA = 0.20  # inner glow band opacity
HALO_ALPHA = 0.62       # neuron halo peak opacity
CORE_ALPHA = 1.0       # core particle opacity
WIRE_ALPHA = 0.55      # connection line opacity
NODE_RING_ALPHA = 0.9

SUPERSAMPLE = 3        # raster supersampling factor for the GIF
GIF_WIDTH = 800
GIF_FPS = 12.5
GIF_DELAY_CS = 8       # 80 ms per frame -> 4.8 s loop
GIF_COLORS = 128      # palette size for the GIF fallback

# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Neuron:
    layer: int
    index: int
    x: float
    y: float
    radius: float


@dataclass(frozen=True)
class Edge:
    index: int
    layer: int            # source layer (0..2), target is layer + 1
    src: Neuron
    dst: Neuron
    launch: float         # absolute time within the cycle when the signal leaves
    signal: str

    @property
    def length(self) -> float:
        return math.hypot(self.dst.x - self.src.x, self.dst.y - self.src.y)


def _wave(index: int, u_src: float, u_dst: float) -> float:
    """Deterministic 0..1 launch offset that sweeps diagonally down the net."""
    noise = (math.sin(index * 12.9898) * 43758.5453) % 1.0 - 0.5
    return min(1.0, max(0.0, 0.58 * u_src + 0.42 * u_dst + 0.055 * noise))


def build_model() -> tuple[list[Neuron], list[Edge]]:
    neurons: list[Neuron] = []
    by_layer: list[list[Neuron]] = []
    for layer, ys in enumerate(LAYER_YS):
        row = [
            Neuron(layer, i, float(LAYER_X[layer]), y, NODE_RADIUS[layer])
            for i, y in enumerate(ys)
        ]
        by_layer.append(row)
        neurons.extend(row)

    edges: list[Edge] = []
    index = 0
    for layer in range(3):
        src_row, dst_row = by_layer[layer], by_layer[layer + 1]
        for src in src_row:
            for dst in dst_row:
                u_src = src.index / max(1, len(src_row) - 1)
                u_dst = dst.index / max(1, len(dst_row) - 1)
                launch = (
                    LAYER_PULSE[layer]
                    + LAUNCH_LAG
                    + SPREAD * _wave(index, u_src, u_dst)
                )
                edges.append(
                    Edge(index, layer, src, dst, launch, EDGE_SIGNAL[layer])
                )
                index += 1
    return neurons, edges


# --------------------------------------------------------------------------
# Animation state
# --------------------------------------------------------------------------


def edge_state(edge: Edge, t: float) -> tuple[float, float] | None:
    """Return (head position 0..1, alpha) for the particle on `edge` at time t."""
    phase = (t - edge.launch) % CYCLE
    if phase < FADE_IN:
        return 0.05, phase / FADE_IN
    if phase < FADE_IN + TRAVEL:
        progress = (phase - FADE_IN) / TRAVEL
        return 0.05 + progress, CORE_ALPHA
    if phase < FADE_IN + TRAVEL + FADE_OUT:
        progress = (phase - FADE_IN - TRAVEL) / FADE_OUT
        return 1.05, CORE_ALPHA * (1.0 - progress)
    return None


def node_state(layer: int, t: float) -> float:
    """Activation 0..1 of every neuron in `layer` at time t."""
    phase = (t - (LAYER_PULSE[layer] - NODE_LEAD)) % CYCLE
    if phase < NODE_RISE:
        return phase / NODE_RISE
    if phase < NODE_FADE:
        return 1.0 - (phase - NODE_RISE) / (NODE_FADE - NODE_RISE)
    return 0.0


# --------------------------------------------------------------------------
# SVG
# --------------------------------------------------------------------------

SVG_STYLE = Template(
    """
  .wire {
    fill: none;
    stroke: $wire;
    stroke-width: 1;
    stroke-opacity: $wire_alpha;
  }

  .sig, .sig-glow, .sig-glow-inner {
    fill: none;
    stroke-linecap: round;
    opacity: 0;
    animation-duration: ${cycle}s;
    animation-iteration-count: infinite;
    animation-timing-function: linear;
    animation-delay: var(--d);
  }
  .sig { stroke-width: $core_width; stroke-dasharray: 5 100; animation-name: nn-signal; }
  .sig-glow {
    stroke-width: $glow_width;
    stroke-dasharray: 13 100;
    animation-name: nn-signal-glow;
  }
  .sig-glow-inner {
    stroke-width: $glow_inner_width;
    stroke-dasharray: 13 100;
    animation-name: nn-signal-glow-inner;
  }

  .set-0 .sig, .set-0 .sig-glow, .set-0 .sig-glow-inner { stroke: $sig; }
  .set-1 .sig, .set-1 .sig-glow, .set-1 .sig-glow-inner { stroke: $sig; }
  .set-2 .sig, .set-2 .sig-glow, .set-2 .sig-glow-inner { stroke: $out_glow; }

  .node-act, .node-halo {
    opacity: 0;
    animation-duration: ${cycle}s;
    animation-iteration-count: infinite;
    animation-timing-function: linear;
    animation-delay: var(--d);
  }
  .node-act { animation-name: nn-node; }
  .node-halo {
    animation-name: nn-halo;
    transform-box: fill-box;
    transform-origin: center;
  }

  .node-base { fill: $node_off; }
  .node-ring { fill: none; stroke-width: 2; stroke-opacity: $ring_alpha; }

  @keyframes nn-signal {
    0%     { stroke-dashoffset: 0;    opacity: 0; }
    $p1%  { stroke-dashoffset: 0;    opacity: $core_alpha; }
    $p2% { stroke-dashoffset: -100; opacity: $core_alpha; }
    $p3% { stroke-dashoffset: -100; opacity: 0; }
    100%   { stroke-dashoffset: 0;    opacity: 0; }
  }
  @keyframes nn-signal-glow {
    0%     { stroke-dashoffset: 13;   opacity: 0; }
    $p1%  { stroke-dashoffset: 13;   opacity: $glow_alpha; }
    $p2% { stroke-dashoffset: -87;  opacity: $glow_alpha; }
    $p3% { stroke-dashoffset: -87;  opacity: 0; }
    100%   { stroke-dashoffset: 13;   opacity: 0; }
  }
  @keyframes nn-signal-glow-inner {
    0%     { stroke-dashoffset: 13;   opacity: 0; }
    $p1%  { stroke-dashoffset: 13;   opacity: $glow_inner_alpha; }
    $p2% { stroke-dashoffset: -87;  opacity: $glow_inner_alpha; }
    $p3% { stroke-dashoffset: -87;  opacity: 0; }
    100%   { stroke-dashoffset: 13;   opacity: 0; }
  }
  @keyframes nn-node {
    0%    { opacity: 0; }
    $n1%  { opacity: 1; }
    $n2%  { opacity: 0; }
    100%  { opacity: 0; }
  }
  @keyframes nn-halo {
    0%    { opacity: 0;    transform: scale(0.62); }
    $n1%  { opacity: $halo_alpha; transform: scale(1); }
    $n2%  { opacity: 0;    transform: scale(1.18); }
    100%  { opacity: 0;    transform: scale(1.18); }
  }

  @media (prefers-reduced-motion: reduce) {
    .sig, .sig-glow, .sig-glow-inner, .node-act, .node-halo { animation: none; opacity: 0; }
  }
"""
)


def _halo_gradient(gid: str, color: str) -> str:
    return (
        f'<radialGradient id="{gid}" cx="0.5" cy="0.5" r="0.5">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.85"/>'
        f'<stop offset="45%" stop-color="{color}" stop-opacity="0.30"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f"</radialGradient>"
    )


def build_svg(neurons: list[Neuron], edges: list[Edge]) -> str:
    style = SVG_STYLE.substitute(
        wire=WIRE,
        wire_alpha=WIRE_ALPHA,
        sig=SIGNAL,
        out_glow=OUTPUT_GLOW,
        node_off=NODE_OFF,
        core_alpha=CORE_ALPHA,
        glow_alpha=GLOW_ALPHA,
        core_width=CORE_WIDTH,
        glow_width=GLOW_WIDTH,
        glow_inner_width=GLOW_INNER_WIDTH,
        glow_inner_alpha=GLOW_INNER_ALPHA,
        halo_alpha=HALO_ALPHA,
        p1=f"{FADE_IN / CYCLE * 100:.3f}",
        p2=f"{(FADE_IN + TRAVEL) / CYCLE * 100:.3f}",
        p3=f"{(FADE_IN + TRAVEL + FADE_OUT) / CYCLE * 100:.3f}",
        n1=f"{NODE_RISE / CYCLE * 100:.3f}",
        n2=f"{NODE_FADE / CYCLE * 100:.3f}",
        ring_alpha=NODE_RING_ALPHA,
        cycle=CYCLE,
    ).strip()

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" role="img" '
        f'aria-labelledby="nn-title nn-desc" shape-rendering="geometricPrecision">'
    )
    out.append(
        '<title id="nn-title">Animated artificial neural network</title>'
        '<desc id="nn-desc">A fully connected feed-forward network with four input '
        "neurons, two hidden layers of six neurons each and two output neurons. "
        "Luminous signals travel left to right from the blue input layer, through "
        "both hidden layers, and into the green output layer, repeating in a "
        "continuous loop.</desc>"
    )

    defs = [
        _halo_gradient("nn-halo-0", INPUT_GLOW),
        _halo_gradient("nn-halo-1", HIDDEN_GLOW),
        _halo_gradient("nn-halo-2", HIDDEN_GLOW),
        _halo_gradient("nn-halo-3", OUTPUT_GLOW),
        (
            '<radialGradient id="nn-bg" cx="0.5" cy="0.47" r="0.62">'
            f'<stop offset="0%" stop-color="{BG_SOFT}" stop-opacity="0.75"/>'
            f'<stop offset="60%" stop-color="{BG_SOFT}" stop-opacity="0.25"/>'
            f'<stop offset="100%" stop-color="{BG_SOFT}" stop-opacity="0"/>'
            "</radialGradient>"
        ),
        f"<style>{style}</style>",
    ]
    out.append("<defs>" + "".join(defs) + "</defs>")

    out.append(
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="{CORNER_RADIUS}" fill="{BG}"/>'
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="{CORNER_RADIUS}" fill="url(#nn-bg)"/>'
    )

    # Connections: static wire + glow tail + core particle, all sharing geometry.
    out.append('<g id="connections">')
    for edge in edges:
        d = (
            f"M{edge.src.x:g} {edge.src.y:g} "
            f"L{edge.dst.x:g} {edge.dst.y:g}"
        )
        delay = edge.launch - CYCLE
        out.append(
            f'<g class="edge set-{edge.layer}" style="--d:{delay:.3f}s">'
            f'<path class="wire" d="{d}" pathLength="100"/>'
            f'<path class="sig-glow" d="{d}" pathLength="100"/>'
            f'<path class="sig-glow-inner" d="{d}" pathLength="100"/>'
            f'<path class="sig" d="{d}" pathLength="100"/>'
            f"</g>"
        )
    out.append("</g>")

    # Neurons: halo + base fill + activation fill + ring.
    out.append('<g id="neurons">')
    for neuron in neurons:
        delay = (LAYER_PULSE[neuron.layer] - NODE_LEAD) - CYCLE
        cx, cy = f"{neuron.x:g}", f"{neuron.y:g}"
        out.append(
            f'<g class="neuron">'
            f'<circle class="node-halo" cx="{cx}" cy="{cy}" '
            f'r="{neuron.radius * HALO_SCALE:g}" fill="url(#nn-halo-{neuron.layer})" '
            f'style="--d:{delay:.3f}s"/>'
            f'<circle class="node-base" cx="{cx}" cy="{cy}" r="{neuron.radius:g}"/>'
            f'<circle class="node-act" cx="{cx}" cy="{cy}" r="{neuron.radius:g}" '
            f'fill="{LAYER_FILL[neuron.layer]}" style="--d:{delay:.3f}s"/>'
            f'<circle class="node-ring" cx="{cx}" cy="{cy}" r="{neuron.radius:g}" '
            f'stroke="{LAYER_FILL[neuron.layer]}"/>'
            f"</g>"
        )
    out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------------
# GIF
# --------------------------------------------------------------------------


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _halo_sprite(color: str, radius: int):
    """Soft radial glow sprite (RGBA) used for neuron halos."""
    import numpy as np
    from PIL import Image

    size = 2 * radius + 1
    yy, xx = np.mgrid[0:size, 0:size]
    dist = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
    alpha = np.clip(1.0 - dist, 0.0, 1.0) ** 2.2
    sprite = np.zeros((size, size, 4), dtype=np.uint8)
    sprite[..., 0], sprite[..., 1], sprite[..., 2] = _rgb(color)
    sprite[..., 3] = (alpha * 255).astype(np.uint8)
    return Image.fromarray(sprite, "RGBA")


def _draw_static(neurons: list[Neuron], edges: list[Edge], scale: int):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (WIDTH * scale, HEIGHT * scale), _rgb(BG) + (255,))
    draw = ImageDraw.Draw(img, "RGBA")

    # Background vignette.
    import numpy as np

    bg = np.asarray(img).copy()
    yy, xx = np.mgrid[0 : HEIGHT * scale, 0 : WIDTH * scale]
    dist = np.sqrt(((xx / (WIDTH * scale) - 0.5) / 0.62) ** 2 + ((yy / (HEIGHT * scale) - 0.47) / 0.62) ** 2)
    falloff = np.clip(1.0 - dist, 0.0, 1.0) ** 1.6
    soft = np.array(_rgb(BG_SOFT), dtype=np.float32)
    base = bg[..., :3].astype(np.float32)
    bg[..., :3] = np.clip(base * (1 - falloff[..., None] * 0.75) + soft * (falloff[..., None] * 0.75), 0, 255).astype(np.uint8)
    img = Image.fromarray(bg, "RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    wire_rgb = _rgb(WIRE)
    for edge in edges:
        draw.line(
            [
                (edge.src.x * scale, edge.src.y * scale),
                (edge.dst.x * scale, edge.dst.y * scale),
            ],
            fill=wire_rgb + (int(255 * WIRE_ALPHA),),
            width=max(1, scale),
        )

    for neuron in neurons:
        cx, cy = neuron.x * scale, neuron.y * scale
        r = neuron.radius * scale
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_rgb(NODE_OFF) + (255,))
        ring = _rgb(LAYER_FILL[neuron.layer])
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=ring + (int(255 * NODE_RING_ALPHA),),
            width=max(1, int(2 * scale)),
        )
    return img


def _draw_frame(base, neurons, edges, t, scale, halo_sprites):
    from PIL import Image, ImageDraw

    frame = base.copy()
    dyn = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(dyn, "RGBA")

    # Neuron activation + halo.
    for neuron in neurons:
        act = node_state(neuron.layer, t)
        if act <= 0.001:
            continue
        cx, cy = neuron.x * scale, neuron.y * scale
        r = neuron.radius * scale
        sprite = halo_sprites[neuron.layer]
        radius = int(round(neuron.radius * HALO_SCALE * scale))
        sprite = sprite.resize((radius * 2 + 1, radius * 2 + 1), Image.LANCZOS)
        alpha = sprite.getchannel("A").point(lambda v, k=act: int(v * k * HALO_ALPHA))
        sprite.putalpha(alpha)
        dyn.alpha_composite(sprite, dest=(int(cx - radius), int(cy - radius)))
        fill = _rgb(LAYER_FILL[neuron.layer])
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r], fill=fill + (int(255 * act),)
        )

    # Signal particles.
    for edge in edges:
        state = edge_state(edge, t)
        if state is None:
            continue
        head, alpha = state
        colour = _rgb(edge.signal)
        dx = edge.dst.x - edge.src.x
        dy = edge.dst.y - edge.src.y
        length = edge.length

        def point(fraction: float) -> tuple[float, float]:
            """Map a 0..1 fraction along the connection to pixel coordinates."""
            return (
                (edge.src.x + dx * fraction) * scale,
                (edge.src.y + dy * fraction) * scale,
            )

        core_lo, core_hi = head - CORE_DASH / 100.0, head
        glow_lo, glow_hi = head - (CORE_DASH + GLOW_DASH) / 100.0, head - CORE_DASH / 100.0

        for lo, hi, width, opacity in (
            (glow_lo, glow_hi, GLOW_WIDTH, GLOW_ALPHA),
            (glow_lo, glow_hi, GLOW_INNER_WIDTH, GLOW_INNER_ALPHA),
            (core_lo, core_hi, CORE_WIDTH, CORE_ALPHA),
        ):
            if hi <= 0 or lo >= 1:
                continue
            lo = max(0.0, lo)
            hi = min(1.0, hi)
            p0, p1 = point(lo), point(hi)
            draw.line([p0, p1], fill=colour + (int(255 * opacity * alpha),), width=max(1, int(width * scale)))
            if width * scale > 3:
                rr = width * scale / 2
                for p in (p0, p1):
                    draw.ellipse(
                        [p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr],
                        fill=colour + (int(255 * opacity * alpha),),
                    )
    return Image.alpha_composite(frame, dyn)


def build_gif(neurons: list[Neuron], edges: list[Edge], path: str) -> None:
    """Render the animation frames and assemble an optimised looping GIF."""
    import shutil
    import subprocess
    import tempfile

    from PIL import Image

    scale = SUPERSAMPLE
    base = _draw_static(neurons, edges, scale)
    halos = {
        layer: _halo_sprite(
            LAYER_GLOW[layer], int(NODE_RADIUS[layer] * HALO_SCALE * scale)
        )
        for layer in range(4)
    }

    frame_count = int(round(CYCLE * GIF_FPS))
    width = GIF_WIDTH
    height = int(round(GIF_WIDTH * HEIGHT / WIDTH))

    workdir = tempfile.mkdtemp(prefix="nn-frames-")
    frames: list[str] = []
    for i in range(frame_count):
        t = i * CYCLE / frame_count
        big = _draw_frame(base, neurons, edges, t, scale, halos)
        target = os.path.join(workdir, f"f{i:04d}.png")
        big.convert("RGB").resize((width, height), Image.LANCZOS).save(target)
        frames.append(target)
        print(f"  frame {i + 1}/{frame_count}", end="\r", file=sys.stderr)
    print(" " * 30, end="\r", file=sys.stderr)

    magick = shutil.which("magick") or shutil.which("convert")
    if magick:
        # One global palette for every frame (no colour flicker), then frame
        # differencing so unchanged pixels are not re-encoded.
        strip = os.path.join(workdir, "strip.png")
        palette = os.path.join(workdir, "palette.png")
        sample = frames[:: max(1, len(frames) // 8)]
        subprocess.run([magick, *sample, "-append", strip], check=True)
        subprocess.run(
            [magick, strip, "-colors", str(GIF_COLORS), "-unique-colors", palette],
            check=True,
        )
        subprocess.run(
            [
                magick,
                "-delay", str(GIF_DELAY_CS),
                "-loop", "0",
                *frames,
                "-remap", palette,
                "-layers", "OptimizeFrame",
                path,
            ],
            check=True,
        )
    else:
        images = [Image.open(f).convert("P", palette=Image.ADAPTIVE, colors=GIF_COLORS) for f in frames]
        images[0].save(
            path,
            save_all=True,
            append_images=images[1:],
            duration=GIF_DELAY_CS,
            loop=0,
            optimize=True,
            disposal=2,
        )

    shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg-only", action="store_true")
    parser.add_argument("--gif-only", action="store_true")
    parser.add_argument(
        "--out",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
        ),
    )
    args = parser.parse_args()

    neurons, edges = build_model()
    os.makedirs(args.out, exist_ok=True)

    if not args.gif_only:
        svg_path = os.path.join(args.out, "neural-network.svg")
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(build_svg(neurons, edges))
        print(f"wrote {svg_path} ({os.path.getsize(svg_path) / 1024:.1f} KB)")

    if not args.svg_only:
        gif_path = os.path.join(args.out, "neural-network.gif")
        try:
            build_gif(neurons, edges, gif_path)
        except ImportError:
            print("Pillow is not installed -- skipped the GIF fallback", file=sys.stderr)
            return 1
        print(f"wrote {gif_path} ({os.path.getsize(gif_path) / 1024:.1f} KB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
