"""Measure fresh CLI invocations; this is not a cold-filesystem or throughput test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev', type=Path, required=True)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=30)
    args = parser.parse_args()
    assert 10 <= args.samples <= 1000
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    engines = {}
    for profile in ['dev', 'release']:
        report = json.loads((getattr(args, profile) / 'qualification.json').read_text())
        assert report['profile'] == profile
        executable = Path(report['workspace']) / 'installed/bin/gwt'
        assert hashlib.sha256(executable.read_bytes()).hexdigest() == report['installedExecutableSha256']
        engines[profile] = {'executable': str(executable), 'sha256': report['installedExecutableSha256'],
                            'toolchain': report['toolchain'], 'engine': report['engine'], 'bytes': executable.stat().st_size}
    assert engines['dev']['toolchain'] == engines['release']['toolchain']
    assert engines['dev']['engine'] == engines['release']['engine']
    environment = {**os.environ, 'PATH': ''}
    workloads = [
        ('invoice', ROOT / 'crates/gwt-core/tests/fixtures/invoice.gwt', 'price invoice',
         {'invoice': {'unit_price': '19.95', 'quantity': 2}}, {'decision': {'status': 'priced', 'total': '47.88'}}),
        ('contact', ROOT / 'examples/native_kind_conditions/rules.gwt', 'review contact',
         json.loads((ROOT / 'examples/native_kind_conditions/request.json').read_text()),
         {'decision': {'status': 'ready', 'channel': 'email', 'destination': 'orders@example.test'}}),
        ('fulfillment', ROOT / 'examples/order_fulfillment/rules.gwt', 'fulfill order',
         json.loads((ROOT / 'examples/order_fulfillment/request.json').read_text()), None),
    ]
    results = []
    for name, source, request, data, expected in workloads:
        fixture = output / name
        fixture.mkdir()
        shutil.copyfile(source, fixture / 'rules.gwt')
        (fixture / 'input.json').write_text(json.dumps(data) + '\n')
        arguments = ['run', str(fixture / 'rules.gwt'), '--request', request, '--input', str(fixture / 'input.json')]
        baseline = None

        def execute(profile, prefix=()):
            started = time.perf_counter_ns()
            result = subprocess.run([*prefix, engines[profile]['executable'], *arguments],
                                    capture_output=True, text=True, env=environment, timeout=30)
            elapsed = time.perf_counter_ns() - started
            assert result.returncode == 0, result.stdout + result.stderr
            observation = json.loads(result.stdout)
            assert observation['ok']
            if baseline is not None:
                assert observation == baseline, (name, profile, 'full observation changed')
            return observation, elapsed / 1_000_000

        baseline, _ = execute('dev')
        execute('release')
        if expected is not None:
            assert baseline['result'] == expected
            independent = {'completeResult': expected}
        else:
            independent = {'fulfillment': {'status': 'partial', 'reason': 'partial_inventory',
                           'requested_units': '4', 'reserved_units': '3', 'backordered_units': '1',
                           'package_count': '1', 'shipping_fee': '19.5'},
                           'inventory': {'widget_available': '4', 'gadget_available': '0', 'cable_available': '4'}}
            for binding, fields in independent.items():
                for field, value in fields.items():
                    assert baseline['result'][binding][field] == value
        encoded = json.dumps(baseline, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        (fixture / 'observation.json').write_bytes(encoded + b'\n')
        passes = []
        for repeat in range(2):
            samples = {'dev': [], 'release': []}
            for index in range(args.samples):
                for profile in (['dev', 'release'] if (index + repeat) % 2 == 0 else ['release', 'dev']):
                    _, elapsed = execute(profile)
                    samples[profile].append(elapsed)
            passes.append({profile: {'milliseconds': values, 'medianMs': statistics.median(values),
                                    'minMs': min(values), 'maxMs': max(values),
                                    'p95Ms': sorted(values)[(95 * len(values) + 99) // 100 - 1]}
                           for profile, values in samples.items()})
        rss = {'dev': [], 'release': []}
        for index in range(3):
            for profile in ['dev', 'release']:
                path = fixture / f'{profile}-rss-{index}.txt'
                execute(profile, ['/usr/bin/time', '-f', '%M', '-o', str(path)])
                rss[profile].append(int(path.read_text().strip()))
        results.append({'name': name, 'request': request, 'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'input': data, 'independentAssertions': independent, 'observationSha256': hashlib.sha256(encoded).hexdigest(),
                        'steps': baseline['steps'], 'eventCount': len(baseline['events']), 'jsonBytes': len(encoded),
                        'passes': passes, 'separatePeakRssKiB': rss})
    report = {'kind': 'gwt.native-process-measurement', 'schemaVersion': 1, 'engines': engines,
              'environment': {'platform': platform.platform(), 'python': platform.python_version(),
                              'cpuAffinity': sorted(os.sched_getaffinity(0)),
                              'cpu': next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), None)},
              'samplesPerProfilePerPass': args.samples, 'passes': 2, 'workloads': results,
              'scope': 'fresh process through stdout capture/decoding; source/input loading, compilation, execution, full evidence and JSON serialization included; verification excluded',
              'limits': ['filesystem and loader caches were not cleared', 'shared machine; CPU affinity/frequency not controlled',
                         'baseline verification invocations precede timed samples', 'RSS uses separate GNU time invocations',
                         'not isolated startup cost, cold-disk latency, throughput, or a language comparison']}
    (output / 'measurements.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'ok': True, 'workloads': [{'name': r['name'], 'medianMs': [{p: s[p]['medianMs'] for p in ['dev', 'release']} for s in r['passes']], 'peakRssKiB': r['separatePeakRssKiB']} for r in results]}))


if __name__ == '__main__':
    main()
