#!/usr/bin/env python3
"""Build ac_frontline using AssaultCube's v10 map format. No extra dependencies."""
from pathlib import Path
import gzip
import struct

ROOT = Path(__file__).resolve().parents[2]
SIZE = 128
SOLID, SPACE = 0, 4
# type, floor, ceiling, wall, floor texture, ceiling texture, vdelta, upper, tag
EARTH, MUD, CONCRETE, WOOD, CRATE, RED, BLUE, GRASS = range(1, 9)
world = [(SOLID, 0, 16, EARTH, MUD, 0, 0, EARTH, 0)] * (SIZE * SIZE)
entities = []


def rect(x1, y1, x2, y2, floor=0, ceil=16, wall=EARTH, tex=MUD, solid=False):
    for y in range(y1, y2):
        for x in range(x1, x2):
            world[y * SIZE + x] = (SOLID if solid else SPACE, floor, ceil,
                                    wall, tex, 0 if ceil == 16 else CONCRETE,
                                    0, wall, 0)


def paired_rect(x1, y1, x2, y2, **kwargs):
    rect(x1, y1, x2, y2, **kwargs)
    rect(SIZE - x2, SIZE - y2, SIZE - x1, SIZE - y1, **kwargs)


def ent(x, y, kind, angle=0, a2=0, a3=0, a4=0):
    floor = world[y * SIZE + x][1]
    entities.append((x, y, floor, angle, kind, a2, a3, a4, 0, 0, 0))


def pair_ent(x, y, kind, angle=0, a2=0, a3=0, a4=0):
    ent(x, y, kind, angle, a2, a3, a4)
    ent(127 - x, 127 - y, kind,
        (angle + 1800) % 3600 if kind in (2, 10, 13) else angle,
        1 - a2 if kind in (2, 13) else a2, a3, a4)


def build():
    # Sunken battlefield; earth banks and solid ruined walls break long sightlines.
    rect(34, 34, 94, 94, floor=2, tex=GRASS)
    paired_rect(42, 47, 57, 57, solid=True, wall=CONCRETE)
    paired_rect(57, 34, 71, 38, solid=True)
    paired_rect(34, 65, 44, 73, solid=True)
    # Dogleg trenches, eight cubes wide, with timber retaining walls.
    for box in [(30, 48, 46, 56), (38, 38, 46, 56), (38, 38, 60, 46),
                (52, 38, 60, 56), (52, 48, 76, 56), (68, 38, 76, 56),
                (68, 38, 90, 46), (82, 38, 90, 56), (82, 48, 98, 56)]:
        paired_rect(*box, floor=-3, wall=WOOD)
    # Central crossroads and shell crater. Shallow terraces can be walked out of.
    rect(44, 59, 84, 69, floor=0)
    rect(54, 48, 74, 80, floor=-3, wall=WOOD)
    rect(56, 56, 72, 72, floor=-2)
    rect(58, 58, 70, 70, floor=-3)
    rect(60, 60, 68, 68, floor=-4)
    # Short stairs between all trench exits and the central direct route.
    for x in range(50, 56):
        paired_rect(x, 59, x + 1, 69, floor=-max(0, x - 52))
    # Mirrored flag compounds: roofed rear shelter, two side exits, front gate.
    paired_rect(20, 44, 36, 84, wall=CONCRETE, tex=CONCRETE)
    paired_rect(20, 55, 30, 73, ceil=9, wall=CONCRETE, tex=CONCRETE)
    paired_rect(20, 44, 24, 53, solid=True, wall=CONCRETE)
    paired_rect(20, 75, 24, 84, solid=True, wall=CONCRETE)
    paired_rect(30, 59, 46, 69, floor=0)
    paired_rect(34, 56, 38, 59, solid=True, wall=CONCRETE)
    paired_rect(34, 69, 38, 72, solid=True, wall=CONCRETE)
    # Broad stairs connect each courtyard to both sunken flanks.
    for x in range(34, 40):
        paired_rect(x, 48, x + 1, 56, floor=-min(3, x - 34), wall=WOOD)
        paired_rect(x, 72, x + 1, 80, floor=-min(3, x - 34), wall=WOOD)
    # Solid blast barriers shield spawns and stop flag-to-flag sniping.
    paired_rect(31, 61, 34, 67, solid=True, wall=CONCRETE)
    paired_rect(45, 60, 48, 64, solid=True, wall=CONCRETE)
    paired_rect(58, 52, 61, 55, solid=True, wall=CONCRETE)
    # Low supply crates and parapets add cover without sealing paths.
    paired_rect(27, 47, 30, 51, floor=3, wall=CRATE, tex=CRATE)
    paired_rect(46, 39, 49, 42, floor=0, wall=CRATE, tex=CRATE)
    paired_rect(57, 60, 59, 64, floor=0, wall=EARTH, tex=EARTH)
    # Faction strips in each flag room.
    rect(21, 58, 24, 70, ceil=9, wall=CONCRETE, tex=RED)
    rect(104, 58, 107, 70, ceil=9, wall=CONCRETE, tex=BLUE)
    pair_ent(26, 64, 13, 900, 0)
    for x, y in [(26, 57), (26, 71), (29, 54), (29, 74), (25, 51), (25, 77)]:
        pair_ent(x, y, 2, 900, 0)
    # FFA starts keep the map usable in the standard non-team map menu, too.
    for x, y in [(40, 41), (56, 50), (41, 64), (30, 80), (49, 84), (64, 75)]:
        ent(x, y, 2, 0, 100)
        ent(127-x, 127-y, 2, 1800, 100)
    for x, y, kind in [(29, 60, 4), (29, 68, 3), (30, 79, 6),
                       (44, 43, 4), (52, 75, 5), (49, 64, 7), (64, 51, 6)]:
        pair_ent(x, y, kind)
    # Small pools of warm light, including the covered shelters.
    for x, y in [(26, 64), (33, 49), (44, 41), (56, 51), (48, 64), (63, 62)]:
        pair_ent(x, y, 1, 24, 180, 170, 145)
        entities[-2] = (*entities[-2][:2], 7, *entities[-2][3:])
        entities[-1] = (*entities[-1][:2], 7, *entities[-1][3:])


def write():
    # sizeof(header) = 980; entities are 16 bytes in v10 (entity.h).
    header = struct.pack('<4s4i128s', b'ACMP', 10, 980, 7, len(entities),
                         b'ac_frontline | Trenches & Outposts | 4v4 CTF')
    header += bytes(range(256)) * 3
    header += struct.pack('<i4B4i10i', -100000, 40, 50, 60, 255,
                          1, 48, 0, 0, *([0] * 10))
    assert len(header) == 980
    data = bytearray(header)
    for e in entities:
        data.extend(struct.pack('<hhhhBBBBhbB', *e))
    previous, repeat = None, 0
    for cell in world:
        record = bytes((0, cell[3], 0)) if cell[0] == SOLID else bytes(v & 255 for v in cell)
        if record == previous and repeat < 255:
            repeat += 1
            continue
        if repeat:
            data.extend((255, repeat))
        data.extend(record)
        previous, repeat = record, 0
    if repeat:
        data.extend((255, repeat))
    dest = ROOT / 'packages/maps/ac_frontline.cgz'
    dest.write_bytes(gzip.compress(data, mtime=0))
    # Dedicated servers scan servermaps, while local clients use packages/maps.
    serverdir = ROOT / 'packages/maps/servermaps'
    (serverdir / dest.name).write_bytes(dest.read_bytes())
    (serverdir / 'ac_frontline.cfg').write_bytes(dest.with_suffix('.cfg').read_bytes())
    print(f'{dest}: {len(data)} decoded bytes, {dest.stat().st_size} compressed bytes; {len(entities)} entities')


if __name__ == '__main__':
    build()
    write()
