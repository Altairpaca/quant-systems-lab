"""Controlled-format smoke measurements with run isolation and provenance capture; not a hardware claim."""
import argparse, csv, hashlib, io, json, os, platform, statistics, subprocess, sys, time
from pathlib import Path

PATTERNS = ('uniform', 'ties', 'bursty', 'skew')
METHODS = ('sort', 'scan', 'heap', 'heap-replace')
COLUMNS = ('repetition', 'method', 'events', 'elapsed_ns')


def command_output(command):
    return subprocess.run(command, text=True, capture_output=True, check=True).stdout.strip()


def parse_rows(text, expected_events):
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise SystemExit('runner error: benchmark produced no rows')
    if tuple(rows[0].keys()) != COLUMNS:
        raise SystemExit(f'runner error: unexpected CSV columns {tuple(rows[0].keys())}')
    for row in rows:
        if row['method'] not in METHODS:
            raise SystemExit(f"runner error: unknown method {row['method']!r}")
        if not row['events'].isdigit() or int(row['events']) != expected_events:
            raise SystemExit(f"runner error: event count {row['events']!r} does not match fixture size {expected_events}")
        if not row['elapsed_ns'].isdigit():
            raise SystemExit(f"runner error: non-numeric elapsed_ns {row['elapsed_ns']!r}")
        if int(row['elapsed_ns']) <= 0:
            raise SystemExit(f"runner error: non-positive elapsed_ns {row['elapsed_ns']!r}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patterns', nargs='+', default=list(PATTERNS))
    parser.add_argument('--feeds', nargs='+', type=int, default=[1, 4, 16, 64])
    parser.add_argument('--total', type=int, default=65536)
    parser.add_argument('--reps', type=int, default=30)
    parser.add_argument('--warmups', type=int, default=2)
    parser.add_argument('--seed', type=int, default=20260912)
    parser.add_argument('--binary', type=Path, default=None)
    parser.add_argument('--rust', type=Path, default=None, help='optional qsl-rust binary; timing is not measured here')
    parser.add_argument('--output-dir', type=Path, default=None)
    parser.add_argument('--source-root', type=Path, default=None)
    args = parser.parse_args()

    root = (args.source_root or Path(__file__).resolve().parents[1]).resolve()
    binary = (args.binary or root / 'build/qsl').resolve()
    if not binary.is_file():
        raise SystemExit(f'runner error: C++ binary missing at {binary}; build it first')
    if args.total < 1:
        raise SystemExit('runner error: --total must be >= 1')
    if args.reps < 1 or args.reps > 1000000:
        raise SystemExit('runner error: --reps must be in 1..1000000')
    if args.warmups < 0 or args.warmups > 1000000:
        raise SystemExit('runner error: --warmups must be in 0..1000000')
    unknown = [p for p in args.patterns if p not in PATTERNS]
    if unknown:
        raise SystemExit(f'runner error: unknown patterns {unknown}; known: {list(PATTERNS)}')
    bad_feeds = [k for k in args.feeds if k < 1 or k > 4096]
    if bad_feeds:
        raise SystemExit(f'runner error: feed counts out of 1..4096: {bad_feeds}')

    run_id = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + hashlib.sha256(
        f'{args.patterns}{args.feeds}{args.total}{args.reps}{args.warmups}{args.seed}'.encode()).hexdigest()[:8]
    output = (args.output_dir or root / 'evidence/runs' / run_id).resolve()
    if output.exists():
        raise SystemExit(f'runner error: output dir already exists: {output}')
    output.mkdir(parents=True)

    def git(*argv):
        try:
            return subprocess.run(['git', '-C', str(root), *argv], text=True, capture_output=True, check=True).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    revision = git('rev-parse', 'HEAD')
    tree = git('rev-parse', 'HEAD^{tree}')
    dirty = git('status', '--porcelain')
    metadata = {
        'run_id': run_id,
        'utc_start': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'source_revision': revision,
        'source_tree': tree,
        'source_dirty': bool(dirty),
        'source_dirty_paths': dirty.splitlines() if dirty else [],
        'binary': str(binary),
        'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'rust_binary': str(args.rust.resolve()) if args.rust else None,
        'rust_binary_sha256': hashlib.sha256(args.rust.read_bytes()).hexdigest() if args.rust and args.rust.is_file() else None,
        'class': 'shared server; batch merge; no exchange or network latency claim',
        'warmups': args.warmups,
        'repetitions': args.reps,
        'seed': args.seed,
        'timed': 'merge plus output allocation; excludes fixture generation/loading, input validation, output comparison/destruction',
        'limits': ['no CPU pinning', 'no thermal/frequency isolation', 'no NUMA placement control'],
        'platform': platform.platform(),
        'machine': platform.machine(),
        'python': platform.python_version(),
        'cpu_model': next((x.split(':', 1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines()
                           if x.startswith('model name')), 'unknown') if Path('/proc/cpuinfo').exists() else 'unknown',
        'logical_cpus': os.cpu_count(),
        'process_affinity': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
        'numa_nodes': sorted(p.name for p in Path('/sys/devices/system/node').glob('node[0-9]*')) if Path('/sys/devices/system/node').exists() else [],
        'scaling_governors': sorted({p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor')}) if Path('/sys/devices/system/cpu').exists() else [],
        'cxx': (lambda result: result.stdout.splitlines()[0] if result.returncode == 0 and result.stdout else 'unknown')(
            subprocess.run(['c++', '--version'], text=True, capture_output=True)),
        'command': ' '.join(sys.argv),
    }
    (output / 'run-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')

    summary = []
    for pattern in args.patterns:
        for feeds in args.feeds:
            event_count = args.total // feeds
            if event_count < 1:
                raise SystemExit(f'runner error: --total {args.total} too small for {feeds} feeds')
            fixture = output / f'fixture-{pattern}-{feeds}.tsv'
            generate = [sys.executable, str(root / 'tools/generate.py'), str(fixture),
                        '--feeds', str(feeds), '--events', str(event_count), '--pattern', pattern, '--seed', str(args.seed)]
            if pattern == 'skew':
                event_count = event_count + (feeds - 1) * (event_count // 100) if feeds > 1 else event_count
            subprocess.run(generate, check=True, timeout=120)
            digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
            rows_in_fixture = sum(1 for line in fixture.read_text().splitlines() if line and not line.startswith('#'))
            bench = [str(binary), 'bench', str(fixture), '--reps', str(args.reps), '--warmups', str(args.warmups)]
            started = time.time()
            result = subprocess.run(bench, text=True, capture_output=True, timeout=1800, check=False)
            elapsed = time.time() - started
            if result.returncode:
                raise SystemExit(f'runner error: bench failed for {pattern}/{feeds}: {result.stderr.strip()[:300]}')
            (output / f'raw-bench-{pattern}-{feeds}.csv').write_text(result.stdout)
            rows = parse_rows(result.stdout, rows_in_fixture)
            for method in METHODS:
                samples = [int(r['elapsed_ns']) / int(r['events']) for r in rows if r['method'] == method]
                if len(samples) != args.reps:
                    raise SystemExit(f'runner error: {pattern}/{feeds}/{method} has {len(samples)} samples, expected {args.reps}')
                summary.append({'pattern': pattern, 'feeds': feeds, 'method': method, 'events': rows_in_fixture,
                                'samples': len(samples), 'median_ns_per_event': statistics.median(samples),
                                'min_ns_per_event': min(samples), 'max_ns_per_event': max(samples),
                                'stdev_ns_per_event': statistics.stdev(samples) if len(samples) > 1 else 0.0,
                                'fixture_sha256': digest, 'generate_command': ' '.join(generate),
                                'bench_command': ' '.join(bench), 'wall_seconds': round(elapsed, 3)})
            fixture.unlink()
    with (output / 'benchmark-summary.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    print(json.dumps({'run_id': run_id, 'output_dir': str(output), 'configurations': len(summary) // len(METHODS),
                      'timed_samples': len(summary) * args.reps, 'repetitions': args.reps,
                      'status': 'per-repetition full-vector comparisons passed'}, indent=2))


if __name__ == '__main__':
    main()
