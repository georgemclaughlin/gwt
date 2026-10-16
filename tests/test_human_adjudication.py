from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from evaluations.human_review.adjudication import load, prepare_assessment, prepare_resolution, reconcile
from evaluations.human_review.study import prepare, score
from tests.test_human_review import synthetic_response


class HumanAdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.packet, self.key = prepare(0, 'synthetic-adjudication')
        self.response = synthetic_response(self.packet, self.key)
        for row in self.response['tasks']:
            row['rationale'] = 'Synthetic explanation: the boundary excludes a valid input. Looks wrong.'
        self.keys, self.responses = [self.key], [self.response]
        self.roster = ['assessor-a', 'assessor-b']

    def sheet(self, assessor, *, roster=None):
        sheet = prepare_assessment(self.keys, self.responses, assessor, assessors=roster or self.roster)
        for row in sheet['rows']:
            if row['context']['status'] != 'submitted':
                row.update(assessment='unavailable', reason='Synthetic absent submission.')
            else:
                row.update(assessment='recognized_defect' if row['context']['revision'] == 'faulty' else 'supported_approval',
                           evidenceQuote='Synthetic explanation', reason='Synthetic assessor judgment for testing only.')
        return sheet

    def reconcile(self, sheets, resolution=None, *, roster=None):
        return reconcile(self.keys, self.responses, sheets, resolution, assessors=roster or self.roster)

    def test_prepare_binds_exact_evidence_and_omits_aggregate_performance(self):
        sheet = prepare_assessment(self.keys, self.responses, 'assessor-a', assessors=self.roster)
        self.assertTrue(all(row['assessment'] is None for row in sheet['rows']))
        text = json.dumps(sheet)
        for omitted in ('median', 'decisionCorrect', 'correctPredictions', 'activeMs', 'confidence'):
            self.assertNotIn(omitted, text)
        self.assertEqual(sheet['rows'][0]['context']['sources'], self.packet['tasks'][0]['sources'])
        self.assertEqual(sheet['rows'][0]['context']['rationale'], self.response['tasks'][0]['rationale'])
        self.assertEqual(sheet['rows'][0]['responseId'], self.response['responseId'])
        self.assertTrue(sheet['rows'][0]['responseDigest'])

    def test_correct_rejection_does_not_become_recognition_without_assessor_judgment(self):
        first, second = self.sheet('assessor-a'), self.sheet('assessor-b')
        faulty = [index for index, row in enumerate(first['rows']) if row['context']['revision'] == 'faulty']
        for sheet in (first, second):
            sheet['rows'][faulty[1]].update(assessment='missed_defect', evidenceQuote='Looks wrong.',
                                          reason='Synthetic unsupported rejection, not recognition.')
        before = score(self.keys, self.responses)
        report = self.reconcile([first, second])
        self.assertEqual(report['summaries'], before['summaries'])
        self.assertEqual(report['summaries']['rehearsal']['overall']['correctSubmittedDecisions'], 4)
        summary = report['rationaleReview']['summaries']['rehearsal']['overall']
        self.assertEqual(summary['assessorJudgedRecognizedDefects'], 1)
        self.assertEqual(summary['finalAssessmentCounts']['missed_defect'], 1)
        self.assertEqual(summary['assessorJudgedSupportedApprovals'], 2)
        self.assertEqual(summary['reviewStatusCounts'], {'consensus': 4})

    def test_absent_assessor_and_incomplete_judgments_never_disappear(self):
        first = self.sheet('assessor-a')
        report = self.reconcile([first])
        self.assertEqual(report['rationaleReview']['missingAssessors'], ['assessor-b'])
        self.assertEqual(report['rationaleReview']['summaries']['rehearsal']['overall']['reviewStatusCounts'], {'single_assessor': 4})
        self.assertTrue(all(row['rationaleAssessment'] == 'pending_manual_review' for row in report['observations']))
        roster = ['assessor-a', 'assessor-b', 'assessor-c']
        report = self.reconcile([self.sheet('assessor-a', roster=roster), self.sheet('assessor-b', roster=roster)], roster=roster)
        self.assertEqual(report['rationaleReview']['summaries']['rehearsal']['overall']['reviewStatusCounts'], {'pending': 4})
        second = self.sheet('assessor-b')
        second['rows'][0].update(assessment=None, evidenceQuote='', reason='')
        report = self.reconcile([first, second])
        self.assertEqual(report['observations'][0]['manualReview']['status'], 'single_assessor')
        self.assertEqual(self.reconcile([])['rationaleReview']['missingAssessors'], self.roster)

    def test_disagreement_requires_explicit_bound_resolution_and_keeps_original_judgments(self):
        first, second = self.sheet('assessor-a'), self.sheet('assessor-b')
        index = next(i for i, row in enumerate(first['rows']) if row['context']['revision'] == 'faulty')
        second['rows'][index]['assessment'] = 'missed_defect'
        pending = self.reconcile([first, second])
        self.assertEqual(pending['observations'][index]['manualReview']['status'], 'needs_resolution')
        resolution = prepare_resolution(self.keys, self.responses, [first, second], 'resolver', assessors=self.roster)
        self.assertEqual(len(resolution['rows']), 1)
        resolution['rows'][0].update(assessment='uncertain', evidenceQuote='', reason='Synthetic unresolved interpretation; retain uncertainty.')
        report = self.reconcile([second, first], resolution)
        row = report['observations'][index]
        self.assertEqual(row['rationaleAssessment'], 'uncertain')
        self.assertEqual(row['manualReview']['status'], 'resolved')
        self.assertEqual(len(row['manualReview']['judgments']), 2)
        self.assertEqual(row['manualReview']['resolution']['resolverId'], 'resolver')
        changed = deepcopy(second)
        changed['rows'][index]['reason'] = 'Changed evidence interpretation later.'
        with self.assertRaises(ValueError):
            self.reconcile([first, changed], resolution)

    def test_invalid_categories_quotes_context_roster_and_duplicate_snapshots_are_refused(self):
        original = self.sheet('assessor-a')
        correct = next(i for i, row in enumerate(original['rows']) if row['context']['revision'] == 'correct')
        faulty = next(i for i, row in enumerate(original['rows']) if row['context']['revision'] == 'faulty')
        changes = [lambda s: s['rows'][correct].update(assessment='recognized_defect'),
                   lambda s: s['rows'][faulty].update(assessment='supported_approval'),
                   lambda s: s['rows'][0].update(evidenceQuote='Invented quotation'),
                   lambda s: s['rows'][0].update(evidenceQuote=''),
                   lambda s: s['rows'][0].update(reason=' '),
                   lambda s: s['rows'][0].update(assessment='unavailable'),
                   lambda s: s['rows'][0].update(assessment=None),
                   lambda s: s['rows'][0]['context'].update(rationale='edited rationale'),
                   lambda s: s['rows'][0].update(responseDigest='stale'),
                   lambda s: s.update(schemaVersion=True),
                   lambda s: s['rows'].reverse(), lambda s: s['rows'].pop(),
                   lambda s: s.update(assessorRoster=['assessor-a']),
                   lambda s: s.update(unknown='ignored?')]
        for change in changes:
            sheet = deepcopy(original)
            change(sheet)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.reconcile([sheet])
        with self.assertRaisesRegex(ValueError, 'duplicate assessor'):
            self.reconcile([original, original])
        with self.assertRaises(ValueError):
            prepare_assessment(self.keys, self.responses, 'unknown', assessors=self.roster)
        with self.assertRaises(ValueError):
            prepare_assessment(self.keys, self.responses, 'assessor-a', assessors=['assessor-a', 'assessor-a'])

    def test_changed_raw_response_or_rubric_invalidates_prior_judgments(self):
        sheet = self.sheet('assessor-a')
        self.response['tasks'][0]['wallMs'] += 1
        with self.assertRaises(ValueError):
            self.reconcile([sheet])
        self.response['tasks'][0]['wallMs'] -= 1
        self.key['answers'][0]['rationaleRubric'] += ' Additional criterion.'
        with self.assertRaises(ValueError):
            self.reconcile([sheet])

    def test_missing_participants_and_skipped_tasks_preserve_denominators_and_no_credit(self):
        _, absent_key = prepare(1, 'planned-absent', 'participant')
        self.keys.append(absent_key)
        self.response['tasks'][0]['status'] = 'skipped'
        first, second = self.sheet('assessor-a'), self.sheet('assessor-b')
        report = self.reconcile([first, second])
        summary = report['rationaleReview']['summaries']['participant']['overall']
        self.assertEqual(summary['plannedTasks'], 4)
        self.assertEqual(summary['submittedTasks'], 0)
        self.assertEqual(summary['finalAssessmentCounts'], {'unavailable': 4})
        self.assertEqual(summary['assessorJudgedRecognizedDefects'], 0)
        self.assertEqual(report['observations'][0]['rationaleAssessment'], 'unavailable')
        changed = deepcopy(first)
        changed['rows'][0].update(assessment='supported_approval', evidenceQuote='Synthetic explanation')
        with self.assertRaises(ValueError):
            self.reconcile([changed, second])

    def test_cli_preserves_inputs_refuses_overwrite_and_strictly_loads_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key, response, output = root/'key.json', root/'response.json', root/'assessment.json'
            key.write_text(json.dumps(self.key))
            response.write_text(json.dumps(self.response))
            command = [sys.executable, '-m', 'evaluations.human_review.adjudication', 'prepare', '--keys', str(key),
                       '--responses', str(response), '--assessors', *self.roster, '--assessor', 'assessor-a', '--output', str(output)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(load(output)['rows'][0]['assessment'], None)
            before = output.read_bytes()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(json.loads(key.read_text()), self.key)
            for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}'):
                output.write_text(text)
                with self.assertRaises(ValueError):
                    load(output)


if __name__ == '__main__':
    unittest.main()
