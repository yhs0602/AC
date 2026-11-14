"""Check the shipped map, independently of its generator. Run with unittest."""
from collections import Counter, deque
from pathlib import Path
import gzip
import re
import struct
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FrontlineMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = gzip.decompress((ROOT / 'packages/maps/ac_frontline.cgz').read_bytes())
        magic, version, offset, factor, count = struct.unpack_from('<4s4i', data)
        assert (magic, version, factor) == (b'ACMP', 10, 7)
        cls.size = 1 << factor
        cls.ents = [struct.unpack_from('<hhhhBBBBhbB', data, offset + i * 16)
                    for i in range(count)]
        offset += count * 16
        cls.cells = []
        while offset < len(data):
            kind = data[offset]
            if kind == 255:
                cls.cells.extend([cls.cells[-1]] * data[offset + 1])
                offset += 2
            elif kind == 0:
                cls.cells.append((0, 0, 16, data[offset+1], 2, 0, 0, data[offset+1], 0))
                offset += 3
            else:
                cell = list(data[offset:offset + 9])
                cell[1:3] = struct.unpack('bb', bytes(cell[1:3]))
                cls.cells.append(tuple(cell))
                offset += 9
        assert len(cls.cells) == cls.size ** 2

    def cell(self, x, y):
        return self.cells[y * self.size + x]

    def clear(self, x, y):
        # Conservative 3x3 footprint and six cubes of standing clearance.
        if not 1 <= x < self.size-1 or not 1 <= y < self.size-1:
            return False
        area = [self.cell(x+dx, y+dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        return all(c[0] != 0 for c in area) and min(c[2] for c in area)-max(c[1] for c in area) >= 6

    def walk(self, start, allowed=lambda x, y: True):
        queue, seen = deque([start]), {start: 0}
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
                if ((nx,ny) not in seen and allowed(nx,ny) and self.clear(nx,ny)
                        and abs(self.cell(nx,ny)[1]-self.cell(x,y)[1]) <= 1):
                    seen[nx,ny] = seen[x,y] + 1
                    queue.append((nx,ny))
        return seen

    def test_ctf_entities_and_clearance(self):
        flags = [e for e in self.ents if e[4] == 13]
        self.assertEqual(Counter(e[5] for e in flags), {0: 1, 1: 1})
        self.assertGreaterEqual(abs(flags[0][0]-flags[1][0]), 24)
        spawns = Counter(e[5] for e in self.ents if e[4] == 2)
        self.assertEqual((spawns[0], spawns[1]), (6, 6))
        reachable = self.walk(flags[0][:2])
        for e in self.ents:
            if e[4] in (2, 3, 4, 5, 6, 7, 8, 13):
                with self.subTest(entity=e):
                    self.assertTrue(self.clear(e[0], e[1]))
                    self.assertIn(e[:2], reachable)

    def test_three_flag_routes(self):
        # Keep only one crossing through the midfield at a time.
        flags = [e[:2] for e in self.ents if e[4] == 13]
        for low, high in ((38, 55), (59, 69), (73, 90)):
            with self.subTest(crossing=(low, high)):
                reachable = self.walk(flags[0], lambda x,y: not 60 <= x <= 67 or low <= y < high)
                self.assertIn(flags[1], reachable)

    def test_rotational_balance(self):
        for y in range(self.size):
            for x in range(self.size):
                a, b = self.cell(x,y), self.cell(127-x,127-y)
                self.assertEqual(a[:3], b[:3], (x,y))

    def test_packaged_textures(self):
        cfg = (ROOT / 'packages/maps/ac_frontline.cfg').read_text()
        for path in re.findall(r'^texture 0 "([^"]+)"', cfg, re.M):
            self.assertTrue((ROOT / 'packages/textures' / path).is_file(), path)
        self.assertLess((ROOT / 'packages/maps/ac_frontline.cgz').stat().st_size, 65536)

    def test_server_copies(self):
        for suffix in ('cgz', 'cfg'):
            filename = f'ac_frontline.{suffix}'
            self.assertEqual((ROOT / 'packages/maps' / filename).read_bytes(),
                             (ROOT / 'packages/maps/servermaps' / filename).read_bytes())


if __name__ == '__main__':
    unittest.main()
