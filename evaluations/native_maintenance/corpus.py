"""Paired native-GWT/Python maintenance corpus; never a participant result."""
from fractions import Fraction
from pathlib import Path

from evaluations.human_review import corpus as review
from evaluations.native_editor.weighted_allocation_oracle import fixtures, cents_text

ROOT = Path(__file__).parent
DOMAINS = (*review.DOMAINS, 'allocation')
GUIDES = {
    'gwt': review.GUIDES['gwt'] + '\n' + (
        'This task uses the experimental Rust GWT engine, not the Python interpreter. '
        'REQUEST input contracts are checked before execution. OUTPUT returns a wrapper keyed '
        'by each output name. REQUIRE failure rejects the policy. Decimal values use exact '
        'arithmetic; / must have a finite decimal result. The explicit step '
        'divide numerator by denominator rounded to 2 places using floor into destination '
        'rounds once into an existing decimal. LET name be expression binds a copied value; '
        'LET name be RecordType: followed by indented fields constructs a record. '
        'A behavior can declare THEN returns Type and RETURN a value; call it with '
        'LET name be behavior arguments. Dotted-path behavior arguments are shared; '
        'parenthesized expressions pass copies. append item to list adds one item. '
        'sum item.field in collection into destination totals fields. FOR item in collection '
        'WHERE condition filters traversal. FIND item in collection WHERE condition takes '
        'the first matching item; ELSE handles no match. Behaviors cannot use arbitrary '
        'Python, list indexing, sorting, or general query syntax. Preserve the supplied '
        'request and output contracts. Embedded scenarios are optional for this comparison; '
        'only independently checked request outcomes determine scores.'),
    'python': (
        'Return complete Python source defining decide(state). Inputs and outputs are the '
        'same JSON objects shown in the task and starter. Use only the Python standard '
        'library. Each call receives fresh copied input. Preserve all output fields and '
        'exact types; bool is distinct from integer. Decimal money is encoded as canonical '
        'strings without trailing zeros, using exact arithmetic rather than binary floats. '
        'For the allocation task only, reject invalid policy inputs by raising '
        'ValueError("policy_rejected"). Other exceptions are execution failures. '
        'Tests are optional; only independently checked request outcomes determine scores.'),
}


def source_path(domain, revision, language):
    folder = ROOT / 'fixtures/allocation' if domain == 'allocation' else review.FIXTURES / domain
    return folder / f'{revision}.{"gwt" if language == "gwt" else "py"}'


def allocation_expected(budget, fallback):
    """Fractional quotas and a single stable ranking, independent of both loops."""
    total = Fraction(budget['total'])
    rows = budget['recipients']
    if total < 0 or (total * 100).denominator != 1 or any(row['weight'] < 0 for row in rows):
        return {'rejected': True}
    effective = [row['weight'] if row['eligible'] else 0 for row in rows]
    if fallback and sum(effective) == 0:
        effective = [int(row['eligible']) for row in rows]
    denominator = sum(effective)
    if total > 0 and not denominator:
        return {'rejected': True}
    cents = int(total * 100)
    quotas = [Fraction(cents * weight, denominator) if denominator else Fraction(0) for weight in effective]
    floors = [quota.numerator // quota.denominator for quota in quotas]
    order = sorted((i for i, weight in enumerate(effective) if weight), key=lambda i: (-(quotas[i] - floors[i]), i))
    winners = set(order[:cents - sum(floors)])
    shares = [{'label': row['label'], 'participates': effective[i] > 0,
               'amount': cents_text(floors[i] + (i in winners)),
               'remainder_score': cents_text(cents * effective[i] - floors[i] * denominator),
               'received_extra_cent': i in winners} for i, row in enumerate(rows)]
    return {'result': {'allocation': {'shares': shares, 'total': cents_text(cents)}}}


def task(domain):
    if domain != 'allocation':
        meta = review.TASKS[domain]
        inputs = [{'facts': facts} for facts in review.probes(domain)]
        public = [{'facts': facts} for facts in meta['inputs']]
        expected = lambda value, new: {'result': review.expected(domain, 'correct' if new else 'baseline', value['facts'])}
        intent = meta['policy'] + '\nRequested change: ' + meta['change'] + '\nContract: ' + meta['schema']
        request = 'assess'
    else:
        inputs = [row['input'] for row in fixtures()['cases']]
        public = [{'budget': {'total': '0.01', 'recipients': [
            {'label': 'first', 'weight': weight, 'eligible': True},
            {'label': 'second', 'weight': weight, 'eligible': True}]}} for weight in [0, 1]]
        inputs += public
        expected = lambda value, new: allocation_expected(value['budget'], new)
        request = 'allocate budget'
        intent = (
            'Change the allocation policy so that, when the sum of eligible weights is zero, '
            'every eligible recipient has effective weight one. Ineligible recipients still '
            'have effective weight zero, regardless of their supplied weight. This fallback '
            'also applies to a zero total, so eligible zero-weight rows participate and expose '
            'the corresponding metadata. If any eligible weight is positive, retain the '
            'existing weights, including zero-weight nonparticipants. Negative weights remain '
            'invalid even for ineligible recipients. A positive total with no eligible '
            'recipients remains rejected; zero total with no eligible recipients succeeds. '
            'Preserve whole-cent/nonnegative budget checks, exact arithmetic, largest-remainder '
            'selection, at most one extra cent per participating row, input-order ties, and '
            'the existing request/output shape and row order. Duplicate labels are not keys. '
            'Compute participates, amount, remainder_score, and received_extra_cent using '
            'effective weights; keep labels and canonical decimal strings unchanged. '
            'Remainder score is total times effective weight minus base amount times total '
            'effective weight, before extra cents. Preserve every behavior unaffected by this change.')
    # Deduplicate public fixtures before scoring; public is a real subset of the corpus.
    unique = []
    for value in inputs + public:
        if value not in unique:
            unique.append(value)
    probes = [{'input': value, 'expected': expected(value, True), 'baseline': expected(value, False),
               'kind': 'changed' if expected(value, True) != expected(value, False) else 'preserved',
               'public': value in public} for value in unique]
    assert {row['kind'] for row in probes} == {'changed', 'preserved'}
    return {'id': domain, 'request': request, 'task': intent, 'probes': probes,
            'publicProbes': [{'input': value, 'expected': expected(value, True)} for value in public]}
