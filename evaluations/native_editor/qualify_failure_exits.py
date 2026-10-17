"""Qualify explicit failure exits, inventory policy, and engine compatibility."""
import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path
import subprocess



def expected(data):
    order, inventory = data['order'], deepcopy(data['inventory'])
    requested = sum(item['quantity'] for item in order['items'])
    result = dict(requested_units=requested, reserved_units=0, backordered_units=0,
                  unknown_sku_count=0, package_count=0, shipping_fee=0,
                  status='held', reason='payment_required')
    if order['payment_status'] == 'paid':
        result['reason'] = 'fraud_review'
        if order['fraud_score'] < 80:
            # Aggregate demand by SKU, reserving against only its first record.
            # This oracle does not reproduce the program's per-order-line loop.
            skus = {item['sku'] for item in order['items']}
            for sku in skus:
                demand = sum(item['quantity'] for item in order['items'] if item['sku'] == sku)
                matches = [item for item in inventory['items'] if item['sku'] == sku]
                if not matches:
                    result['unknown_sku_count'] += sum(item['sku'] == sku for item in order['items'])
                    continue
                stock = matches[0]
                reserved = min(stock['available'], demand)
                stock['available'] -= reserved
                stock['reserved'] += reserved
                result['reserved_units'] += reserved
                result['backordered_units'] += demand - reserved
            units = result['reserved_units']
            if result['unknown_sku_count']:
                result['status'], result['reason'] = 'held', 'unknown_sku'
            else:
                result['status'], result['reason'] = (
                    ('backordered', 'no_inventory') if units == 0 else
                    ('partial', 'partial_inventory') if result['backordered_units'] else
                    ('ready', 'ready_to_ship'))
                result['package_count'] = 0 if units == 0 else 1 if units <= 3 else 2 if units <= 6 else 3
                result['shipping_fee'] = (0 if units == 0 else
                                         Decimal(15) + Decimal('1.5') * units if order['expedited'] else
                                         0 if units >= 5 else 6 + units)
    return {'fulfillment': result, 'inventory': inventory}


def canonical(value):
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    if type(value) in (int, float, Decimal):
        return format(Decimal(str(value)).normalize(), 'f')
    return value


def python_matches(actual, wanted):
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and actual.keys() == wanted.keys() and all(
            python_matches(actual[k], v) for k, v in wanted.items())
    if isinstance(wanted, list):
        return isinstance(actual, list) and len(actual) == len(wanted) and all(
            python_matches(a, b) for a, b in zip(actual, wanted))
    if type(wanted) in (int, float, Decimal):
        return type(actual) in (int, float, Decimal) and canonical(actual) == canonical(wanted)
    return type(actual) is type(wanted) and actual == wanted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--previous-engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    native, previous = args.native.resolve(), args.previous_engine.resolve()
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (native, previous)}
    commands = []

    def save(name, value):
        path = root / name
        path.write_text(json.dumps(value, indent=2, default=str) + '\n')
        return path

    def call(engine, *arguments, code=0):
        result = subprocess.run([str(engine), *map(str, arguments)], text=True, capture_output=True, timeout=60)
        commands.append({'command': [str(engine), *map(str, arguments)], 'exitCode': result.returncode, 'stderr': result.stderr})
        save('commands.json', commands)
        assert result.returncode == code, (arguments, result.stdout[:1500], result.stderr)
        return json.loads(result.stdout)

    entry = Path('examples/inventory_allocation_spike/native_scenarios.gwt')
    observations = []
    for paid, fraud, expedited, stock, quantity, shape, unknown in itertools.product(
            (False, True), (79, 80), (False, True), (0, 1, 2, 3, 7), (1, 2, 4),
            ('empty', 'other', 'duplicates'), (False, True)):
        items = ([] if shape == 'empty' else [{'sku': 'other', 'available': 100, 'reserved': 0}] if shape == 'other' else
                 [{'sku': 'widget', 'available': stock, 'reserved': 1}, {'sku': 'widget', 'available': 100, 'reserved': 2}])
        order_items = [{'sku': 'widget', 'quantity': quantity}] * 2
        if unknown:
            order_items += [{'sku': 'missing', 'quantity': 1}]
        data = {'order': {'order_id': 'synthetic', 'payment_status': 'paid' if paid else 'declined',
                          'fraud_score': fraud, 'expedited': expedited, 'items': order_items},
                'inventory': {'items': items}}
        oracle = expected(data)
        input_path = save('current-input.json', data)
        run = call(native, 'run', entry, '--request', 'fulfill order', '--input', input_path)
        assert run['ok'] and run['result'] == canonical(oracle), (data, run)
        observations.append({'input': data, 'expected': oracle, 'matchesIndependentOracle': True})
    save('inventory-observations.json', observations)
    save('native-validation.json', call(native, 'validate', entry))

    compatibility_source = 'RECORD Box\n  value: optional<integer>\nREQUEST choose\n  GIVEN box is Box\n  GIVEN replacement is Box\n  WHEN choose box through box with replacement\n  OUTPUT box is Box\nWHEN choose <box> through <alias> with <replacement>\n  GIVEN box is Box\n  AND alias is Box\n  AND replacement is Box\n  IF box.value is absent\n    REQUIRE false\n  set alias to replacement\n'
    compatibility = []
    for label, replacement in [('clearing', {}), ('present', {'value': 7}), ('redundant', {})]:
        path = root / (label + '.gwt')
        path.write_text(compatibility_source.replace('  set alias to replacement\n', '  REQUIRE box.value is present\n') if label == 'redundant' else compatibility_source)
        input_path = save(label + '-input.json', {'box': {'value': 2}, 'replacement': replacement})
        old_case = call(previous, 'capture', path, '--request', 'choose', '--input', input_path)
        assert old_case['record']['observed']['ok']
        saved = save(label + '-old-case.json', old_case)
        proposal = call(native, 'migrate', saved, '--previous-engine', previous, code=1 if label == 'redundant' else 0)
        save(label + '-migration.json', proposal)
        assert not proposal['approved']
        assert proposal['status'] == {'clearing': 'observation_changed', 'present': 'observation_preserved', 'redundant': 'candidate_unavailable'}[label]
        if label != 'redundant':
            migrated = save(label + '-candidate.json', proposal['candidate'])
            assert call(native, 'replay', migrated)['verified']
        if label == 'clearing':
            observed = proposal['candidate']['record']['observed']
            assert observed['diagnostic']['code'] == 'presence_mutation'
            assert observed['state']['box']['value'] == 2
        compatibility.append({'probe': label, 'status': proposal['status']})

    for index in range(57):
        old_case = Path('evaluations/native_editor/2026-10-16-branch-proofs/workflow') / f'portfolio-candidate-{index}.json'
        before_bytes = old_case.read_bytes()
        migration = call(native, 'migrate', old_case, '--previous-engine', previous)
        assert migration['status'] == 'observation_preserved' and not migration['approved']
        assert old_case.read_bytes() == before_bytes
        save(f'portfolio-migration-{index}.json', migration)
        saved = save(f'portfolio-candidate-{index}.json', migration['candidate'])
        assert call(native, 'replay', saved)['verified']
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in hashes.items())
    report = {'inventoryInputs': len(observations), 'inventoryExecutions': len(observations),
              'preservedPortfolioMigrations': 57, 'compatibility': compatibility,
              'executableHashes': hashes, 'proposalsApproved': False, 'humanParticipants': 0}
    save('qualification.json', report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
