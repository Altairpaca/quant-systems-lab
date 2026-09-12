"""Public synthetic availability-ordered feed fixture; no market data."""
import argparse
from pathlib import Path
MASK = (1 << 64) - 1
class SplitMix64:
    def __init__(self, seed: int): self.state = seed & MASK
    def next(self) -> int:
        self.state = (self.state + 0x9e3779b97f4a7c15) & MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xbf58476d1ce4e5b9) & MASK
        z = ((z ^ (z >> 27)) * 0x94d049bb133111eb) & MASK
        return z ^ (z >> 31)
def main():
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path); p.add_argument('--feeds', type=int, default=16)
    p.add_argument('--events', type=int, default=10000); p.add_argument('--seed', type=int, default=1701)
    p.add_argument('--pattern', choices=['uniform', 'ties', 'bursty', 'skew'], default='uniform')
    a = p.parse_args()
    if not 0 <= a.feeds <= 4096 or a.events < 0: p.error('invalid fixture size')
    rng = SplitMix64(a.seed)
    with a.output.open('w') as out:
        out.write('# available_ns feed_id sequence venue_ns price_ticks qty\n')
        for f in range(a.feeds):
            t = 0
            n = a.events if a.pattern != 'skew' or f == 0 else a.events // 100
            for i in range(n):
                delta = rng.next() % (1 if a.pattern == 'ties' else 11)
                if a.pattern == 'bursty': delta = 0 if i % 64 else 1000
                t += delta
                out.write(f'{t}\t{f}\t{i}\t{t - 100}\t{10000 + rng.next()%20}\t{1+rng.next()%100}\n')
if __name__ == '__main__': main()
