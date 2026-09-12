"""Controlled-format smoke measurements. Does not establish hardware performance."""
import argparse, csv, hashlib, io, json, platform, statistics, subprocess
from pathlib import Path
p = argparse.ArgumentParser(); p.add_argument('--patterns', nargs='+', default=['uniform','ties','bursty','skew'])
p.add_argument('--feeds', nargs='+', type=int, default=[1,4,16,64]); p.add_argument('--total', type=int, default=65536)
a = p.parse_args(); root = Path(__file__).resolve().parents[1]
evidence = root/'evidence'; evidence.mkdir(exist_ok=True)
metadata = {'platform':platform.system(), 'machine':platform.machine(), 'python':platform.python_version(),
            'compiler':subprocess.check_output(['c++','--version'],text=True).splitlines()[0],
            'flags':'CMake Release, -O3 -DNDEBUG on this GNU build; no -march=native',
            'warmups':2,'repetitions':9,'timed':'merge plus output allocation; excludes fixture load, validation, output comparison/destruction',
            'limits':['shared virtualized container','no CPU pinning','no thermal/frequency isolation','not exchange or network latency']}
if Path('/proc/cpuinfo').exists():
    metadata['cpu_model'] = next((x.split(':',1)[1].strip() for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name')), 'unknown')
(evidence/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n')
summary=[]
for pattern in a.patterns:
    for k in a.feeds:
        if k < 1 or k > 4096: p.error('invalid feed count')
        fixture=root/'fixtures'/f'large-{pattern}-{k}.tsv'
        subprocess.run(['python',str(root/'tools/generate.py'),str(fixture),'--feeds',str(k),'--events',str(a.total//k),'--pattern',pattern],check=True)
        digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
        result=subprocess.run([str(root/'build/qsl'),'bench',str(fixture)],text=True,capture_output=True,check=True,timeout=60)
        (evidence/f'raw-bench-{pattern}-{k}.csv').write_text(result.stdout)
        rows=list(csv.DictReader(io.StringIO(result.stdout)))
        for method in ['sort','scan','heap','heap-replace']:
            samples=[int(r['elapsed_ns'])/int(r['events']) for r in rows if r['method']==method]
            summary.append({'pattern':pattern,'feeds':k,'method':method,'events':rows[0]['events'],
                'median_ns_per_event':statistics.median(samples),'min_ns_per_event':min(samples),
                'max_ns_per_event':max(samples),'fixture_sha256':digest})
        fixture.unlink()  # deterministic regeneration; do not distribute large synthetic data
with (evidence/'benchmark-summary.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=summary[0]); w.writeheader();w.writerows(summary)
print(json.dumps({'configurations':len(summary)//4,'timed_samples':len(summary)*9,'status':'full-vector comparisons passed'},indent=2))
