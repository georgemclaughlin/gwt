import unittest

from evaluations.native_maintenance.corpus import DOMAINS, allocation_expected, source_path, task
from evaluations.native_maintenance.study import exact, partition, prepare


class NativeMaintenanceTests(unittest.TestCase):
    def test_pairing_and_prompt_boundary_keep_only_public_expectations(self):
        prepared = prepare()
        self.assertEqual(len(prepared), 30)
        self.assertEqual(len({row['caseId'] for row in prepared}), 30)
        for index in range(0, len(prepared), 2):
            pair = prepared[index:index + 2]
            self.assertEqual({row['language'] for row in pair}, {'gwt', 'python'})
            self.assertEqual(pair[0]['task'], pair[1]['task'])
            self.assertEqual(pair[0]['context']['publicProbes'], pair[1]['context']['publicProbes'])
            for row in pair:
                self.assertEqual(row['context']['source'], source_path(row['pairId'], 'baseline', row['language']).read_text())
                self.assertEqual(len(row['context']['publicProbes']), 2)
                self.assertNotIn('probes', row)
                self.assertNotIn('baseline', row['context'])
                self.assertNotIn('gold', row['context'])
                self.assertEqual(row['context']['executionEngine'], 'native-gwt' if row['language'] == 'gwt' else 'python')
        for invalid in [0, -1, True, 1.5]:
            with self.assertRaises(ValueError):
                prepare(invalid)

    def test_corpus_has_unique_inputs_changed_preserved_and_public_subsets(self):
        for domain in DOMAINS:
            spec = task(domain)
            probes = spec['probes']
            self.assertEqual({row['kind'] for row in probes}, {'changed', 'preserved'})
            self.assertEqual(sum(row['public'] for row in probes), 2)
            for index, probe in enumerate(probes):
                self.assertNotIn(probe['input'], [row['input'] for row in probes[:index]])
                self.assertEqual(probe['kind'] == 'changed', not exact(probe['expected'], probe['baseline']))

    def test_fallback_policy_covers_ties_metadata_exclusion_and_rejections(self):
        rows = [{'label': 'same', 'weight': 0, 'eligible': True},
                {'label': 'same', 'weight': 0, 'eligible': True},
                {'label': 'ignored', 'weight': 99, 'eligible': False}]
        budget = {'total': '0.01', 'recipients': rows}
        self.assertEqual(allocation_expected(budget, False), {'rejected': True})
        result = allocation_expected(budget, True)['result']['allocation']
        self.assertEqual(result['total'], '0.01')
        self.assertEqual(result['shares'], [
            {'label': 'same', 'participates': True, 'amount': '0.01', 'remainder_score': '0.01', 'received_extra_cent': True},
            {'label': 'same', 'participates': True, 'amount': '0', 'remainder_score': '0.01', 'received_extra_cent': False},
            {'label': 'ignored', 'participates': False, 'amount': '0', 'remainder_score': '0', 'received_extra_cent': False},
        ])
        budget['total'] = '0'
        shares = allocation_expected(budget, True)['result']['allocation']['shares']
        self.assertEqual([row['participates'] for row in shares], [True, True, False])
        self.assertEqual([row['amount'] for row in shares], ['0', '0', '0'])
        budget['recipients'][0]['weight'] = 1
        self.assertEqual(allocation_expected(budget, True), allocation_expected(budget, False))
        budget['recipients'][2]['weight'] = -1
        self.assertEqual(allocation_expected(budget, True), {'rejected': True})
        for total, rejected in [('0.01', True), ('-0.01', True), ('0.001', True), ('0', False)]:
            outcome = allocation_expected({'total': total, 'recipients': []}, True)
            self.assertEqual('rejected' in outcome, rejected)

    def test_scoring_does_not_coerce_types_or_drop_missing_observations(self):
        for actual, expected in [(True, 1), ('1', 1), (1.0, 1), ({}, {'field': None}),
                                 ({'result': {}}, {'rejected': True}), ([1, 2], [1]),
                                 ({'error': 'assertion_failed'}, {'rejected': True})]:
            self.assertFalse(exact(actual, expected))
        spec = task('allocation')
        probes = spec['probes']
        baseline = partition(probes, [row['baseline'] for row in probes])
        self.assertEqual(baseline['changed']['passed'], 0)
        self.assertEqual(baseline['preserved']['passed'], baseline['preserved']['total'])
        correct = partition(probes, [row['expected'] for row in probes])
        self.assertEqual(correct['all']['passed'], correct['all']['total'])
        with self.assertRaises(ValueError):
            partition(probes, [])


if __name__ == '__main__':
    unittest.main()
