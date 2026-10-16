"""Record manual rationale judgments without treating decisions as defect recognition."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re

from .study import digest, score, write_json


CATEGORIES = {'recognized_defect', 'missed_defect', 'supported_approval',
              'unsupported_or_incorrect', 'uncertain', 'unavailable'}
EDITABLE = ('assessment', 'evidenceQuote', 'reason')


def opaque_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
        raise ValueError('use an opaque assessor/resolver ID of 1–64 letters, digits, underscores or hyphens')
    return value


def roster_ids(values):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError('declare the nonempty planned assessor roster')
    roster = [opaque_id(value) for value in values]
    if len(set(roster)) != len(roster):
        raise ValueError('duplicate planned assessor')
    return sorted(roster)


def load(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError('input file exceeds 32 MiB')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('duplicate JSON field')
            value[key] = item
        return value
    def constant(value):
        raise ValueError('nonfinite JSON value')
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    digest(value)  # Also rejects numeric overflow to nonfinite host floats.
    return value


def materials(keys, responses):
    report = score(keys, responses)  # Revalidate raw evidence; never trust an edited score report.
    keyed = {key['packet']['packetId']: key for key in keys}
    observed = {response['packetId']: response for response in responses}
    identity = {'keys': {packet: digest(key) for packet, key in sorted(keyed.items())},
                'responses': {packet: digest(response) for packet, response in sorted(observed.items())}}
    rows = []
    for observation in report['observations']:
        packet = observation['packetId']
        key, response = keyed[packet], observed.get(packet)
        task = next(task for task in key['packet']['tasks'] if task['id'] == observation['taskId'])
        rows.append({'packetId': packet, 'taskId': task['id'], 'purpose': observation['purpose'],
                     'responseId': response['responseId'] if response else None,
                     'responseDigest': digest(response) if response else None, 'keyDigest': digest(key),
                     'context': {'domain': task['domain'], 'language': task['language'],
                                 'policy': task['policy'], 'change': task['change'], 'schema': task['schema'],
                                 'sources': deepcopy(task['sources']), 'revision': observation['revision'],
                                 'status': observation['status'], 'recommendation': observation['recommendation'],
                                 'rationale': observation['rationale'], 'rubric': observation['rationaleRubric']}})
    return report, identity, rows


def blank(row):
    return {**deepcopy(row), 'assessment': None, 'evidenceQuote': '', 'reason': ''}


def prepare_assessment(keys, responses, assessor, *, assessors):
    _, identity, rows = materials(keys, responses)
    roster = roster_ids(assessors)
    if opaque_id(assessor) not in roster:
        raise ValueError('assessor is not in the planned roster')
    return {'kind': 'gwt.human-rationale-assessment', 'schemaVersion': 1,
            'studyDigest': digest(identity), 'assessorId': assessor, 'assessorRoster': roster,
            'rows': [blank(row) for row in rows]}


def validate_judgment(row):
    category, quote, reason = row['assessment'], row['evidenceQuote'], row['reason']
    if not isinstance(quote, str) or not isinstance(reason, str) or len(quote) > 20000 or len(reason) > 20000:
        raise ValueError('evidence quote and reason must be strings of at most 20000 characters')
    if category is None:
        if quote or reason:
            raise ValueError('pending judgments must leave quote and reason empty')
        return
    if not isinstance(category, str) or category not in CATEGORIES or not reason.strip():
        raise ValueError('completed judgment needs a recognized category and written reason')
    context = row['context']
    if context['status'] != 'submitted':
        if category != 'unavailable' or quote:
            raise ValueError('unsubmitted work can only be unavailable, with no credited quote')
        return
    if category == 'unavailable':
        raise ValueError('submitted rationale must be assessed or left pending/uncertain')
    if category in ('recognized_defect', 'missed_defect') and context['revision'] != 'faulty':
        raise ValueError('defect recognition/miss categories require a faulty candidate')
    if category == 'supported_approval' and (context['revision'] != 'correct' or context['recommendation'] != 'approve'):
        raise ValueError('supported approval requires approval of a correct candidate')
    if category != 'uncertain' and not quote.strip():
        raise ValueError('this judgment needs an exact evidence quote')
    if quote and (not quote.strip() or quote not in context['rationale']):
        raise ValueError('evidence quote must occur verbatim in the recorded rationale')


def validate_sheet(sheet, template):
    if not isinstance(sheet, dict) or set(sheet) != set(template):
        raise ValueError('unexpected assessment/resolution fields')
    # Canonical digests preserve exact types (including bool vs integer).
    if digest({key: value for key, value in sheet.items() if key != 'rows'}) != digest(
            {key: value for key, value in template.items() if key != 'rows'}):
        raise ValueError('assessment/resolution identity mismatch')
    if not isinstance(sheet['rows'], list) or len(sheet['rows']) != len(template['rows']):
        raise ValueError('all planned rows must remain in assigned order')
    for row, expected in zip(sheet['rows'], template['rows']):
        if not isinstance(row, dict) or set(row) != set(expected):
            raise ValueError('unexpected judgment fields')
        if digest({key: value for key, value in row.items() if key not in EDITABLE}) != digest(
                {key: value for key, value in expected.items() if key not in EDITABLE}):
            raise ValueError('judgment context or evidence identity changed')
        validate_judgment(row)


def validated_assessments(keys, responses, sheets, assessors):
    roster = roster_ids(assessors)
    by_assessor = dict.fromkeys(roster)
    for sheet in sheets:
        if not isinstance(sheet, dict):
            raise ValueError('assessment must be an object')
        assessor = opaque_id(sheet.get('assessorId'))
        if assessor not in by_assessor:
            raise ValueError('unplanned assessor')
        if by_assessor[assessor] is not None:
            raise ValueError('duplicate assessor; select one explicit snapshot per assessor')
        validate_sheet(sheet, prepare_assessment(keys, responses, assessor, assessors=roster))
        by_assessor[assessor] = sheet
    return dict(sorted(by_assessor.items()))


def opinions(sheets, index):
    return [{'assessorId': assessor, 'missingSheet': sheet is None,
             **({field: sheet['rows'][index][field] for field in EDITABLE} if sheet is not None else
                {'assessment': None, 'evidenceQuote': '', 'reason': ''})}
            for assessor, sheet in sheets.items()]


def review_status(judgments):
    filled = [row for row in judgments if row['assessment'] is not None]
    if not filled:
        return 'pending'
    if len(filled) == 1:
        return 'single_assessor'
    if len(filled) < len(judgments):
        return 'pending'
    return 'consensus' if len({row['assessment'] for row in filled}) == 1 else 'needs_resolution'


def resolution_template(identity, rows, sheets, resolver):
    conflicts = []
    for index, row in enumerate(rows):
        judgments = opinions(sheets, index)
        if review_status(judgments) == 'needs_resolution':
            conflicts.append(blank({**row, 'judgments': judgments}))
    return {'kind': 'gwt.human-rationale-resolution', 'schemaVersion': 1,
            'studyDigest': digest(identity), 'assessmentSetDigest': digest(sheets),
            'assessorRoster': list(sheets), 'resolverId': opaque_id(resolver), 'rows': conflicts}


def prepare_resolution(keys, responses, assessments, resolver, *, assessors):
    _, identity, rows = materials(keys, responses)
    sheets = validated_assessments(keys, responses, assessments, assessors)
    return resolution_template(identity, rows, sheets, resolver)


def reconcile(keys, responses, assessments, resolution=None, *, assessors):
    report, identity, rows = materials(keys, responses)
    sheets = validated_assessments(keys, responses, assessments, assessors)
    resolved = {}
    if resolution is not None:
        if not isinstance(resolution, dict):
            raise ValueError('resolution must be an object')
        template = resolution_template(identity, rows, sheets, resolution.get('resolverId'))
        validate_sheet(resolution, template)
        resolved = {(row['packetId'], row['taskId']): row for row in resolution['rows']}
    for index, observation in enumerate(report['observations']):
        judgments = opinions(sheets, index)
        status = review_status(judgments)
        final = judgments[0]['assessment'] if status == 'consensus' else None
        decision = resolved.get((observation['packetId'], observation['taskId']))
        resolution_record = None
        if decision and decision['assessment'] is not None:
            status, final = 'resolved', decision['assessment']
            resolution_record = {'resolverId': resolution['resolverId'],
                                 **{field: decision[field] for field in EDITABLE}}
        observation['rationaleAssessment'] = final or 'pending_manual_review'
        observation['manualReview'] = {'status': status, 'judgments': judgments, 'resolution': resolution_record}

    def summarize(selected):
        finalized = [row for row in selected if row['manualReview']['status'] in ('consensus', 'resolved')]
        return {'plannedTasks': len(selected), 'submittedTasks': sum(row['status'] == 'submitted' for row in selected),
                'plannedFaultyTasks': sum(row['revision'] == 'faulty' for row in selected),
                'submittedFaultyTasks': sum(row['revision'] == 'faulty' and row['status'] == 'submitted' for row in selected),
                'reviewStatusCounts': dict(Counter(row['manualReview']['status'] for row in selected)),
                'finalAssessmentCounts': dict(Counter(row['rationaleAssessment'] for row in finalized)),
                'assessorJudgedRecognizedDefects': sum(row['rationaleAssessment'] == 'recognized_defect' for row in finalized),
                'assessorJudgedSupportedApprovals': sum(row['rationaleAssessment'] == 'supported_approval' for row in finalized)}
    summaries = {}
    for purpose in ('participant', 'rehearsal'):
        selected = [row for row in report['observations'] if row['purpose'] == purpose]
        summaries[purpose] = {'overall': summarize(selected), 'byLanguage': {
            language: summarize([row for row in selected if row['language'] == language]) for language in ('gwt', 'python')}}
    report['rationaleReview'] = {'studyDigest': digest(identity), 'evidenceDigests': identity,
                                'assessorRoster': list(sheets),
                                'missingAssessors': [assessor for assessor, sheet in sheets.items() if sheet is None],
                                'assessmentDigests': {assessor: digest(sheet) if sheet is not None else None for assessor, sheet in sheets.items()},
                                'resolutionDigest': digest(resolution) if resolution is not None else None,
                                'summaries': summaries}
    report['limitations'] += [
        'Rationale categories are assessor judgments; exact quotes and checksums do not verify their semantic accuracy.',
        'Final categories require agreement from at least two supplied assessors or an explicit resolution of their disagreement.',
        'Opaque assessor IDs do not authenticate identity or establish independent assessment; retain the assessor assignment log.',
        'Single-assessor, incomplete and unresolved judgments receive no final recognition credit; original decision counts are unchanged.']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'prepare-resolution', 'reconcile'):
        command = commands.add_parser(name)
        command.add_argument('--keys', type=Path, nargs='+', required=True)
        command.add_argument('--responses', type=Path, nargs='*', default=[])
        command.add_argument('--output', type=Path, required=True)
        command.add_argument('--assessors', nargs='+', required=True, help='Complete planned assessor roster, including missing sheets')
        if name == 'prepare':
            command.add_argument('--assessor', required=True)
        else:
            command.add_argument('--assessments', type=Path, nargs='*', default=[])
        if name == 'prepare-resolution':
            command.add_argument('--resolver', required=True)
        if name == 'reconcile':
            command.add_argument('--resolution', type=Path)
    args = parser.parse_args()
    keys, responses = [load(path) for path in args.keys], [load(path) for path in args.responses]
    if args.command == 'prepare':
        result = prepare_assessment(keys, responses, args.assessor, assessors=args.assessors)
    else:
        sheets = [load(path) for path in args.assessments]
        if args.command == 'prepare-resolution':
            result = prepare_resolution(keys, responses, sheets, args.resolver, assessors=args.assessors)
        else:
            result = reconcile(keys, responses, sheets, load(args.resolution) if args.resolution else None, assessors=args.assessors)
    write_json(args.output, result)  # Never overwrite raw evidence or prior adjudication snapshots.
    print(f'Wrote {args.command} artifact: {args.output}')


if __name__ == '__main__':
    main()
