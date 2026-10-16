"""Independent rational oracle for the illustrative native underwriting policy.

No GWT runtime imports. Ratios are evaluated as Fraction quotients, independently
of the source's cross-multiplied comparisons. Output pairs remain unreduced.
"""
from decimal import Decimal, localcontext
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path


def text(value):
    value = F(value)
    denominator = value.denominator
    for prime in (2, 5):
        while denominator % prime == 0:
            denominator //= prime
    assert denominator == 1, value
    with localcontext() as context:
        context.prec = 150
        result = format(Decimal(value.numerator) / Decimal(value.denominator), 'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def application(**changes):
    result = dict(credit_score='780', annual_income='120000', monthly_debt='1500',
                  home_price='400000', down_payment='100000', available_cash='140000',
                  late_payments=[], collections=[], bankruptcies='0', employment_years='5')
    result.update(changes)
    return result


def expected(a):
    v = {k: F(value) for k, value in a.items() if not isinstance(value, list)}
    principal = v['home_price'] - v['down_payment']
    assert min(v['annual_income'], v['home_price'], principal) > 0
    pairs = dict(dti=(v['monthly_debt'] * 12, v['annual_income']),
                 ltv=(principal, v['home_price']),
                 reserve_months=(v['available_cash'] - v['down_payment'], principal * F('0.006')))
    dti, ltv, reserve = (F(*pair) for pair in pairs.values())
    credit = v['credit_score']
    risk = (0 if credit >= 760 else 1 if credit >= 700 else 2 if credit >= 660 else 5)
    risk += next(points for limit, points in [(F('.36'), 0), (F('.43'), 1), (F('.50'), 3), (None, 6)] if limit is None or dti <= limit)
    risk += next(points for limit, points in [(F('.8'), 0), (F('.9'), 1), (F('.97'), 3), (None, 5)] if limit is None or ltv <= limit)
    risk += (8 if v['bankruptcies'] > 0 else 0) + (0 if v['employment_years'] >= 2 else 2)
    risk += sum(map(F, a['late_payments'] + a['collections']))
    # Independent ordered policy table over rational quotients.
    eligible = [(v['bankruptcies'] > 0 and credit < 700, 'denied', 'recent_bankruptcy'),
                (risk <= 4 and dti <= F('.43') and ltv <= F('.90') and reserve >= 3, 'approved', 'strong_application'),
                (risk <= 8 and dti <= F('.50') and ltv <= F('.97') and reserve >= 1, 'manual_review', 'compensating_factors'),
                (True, 'denied', 'risk_too_high')]
    _, status, reason = next(row for row in eligible if row[0])
    rate = '6.25' if status == 'approved' and risk <= 2 else '6.5' if status == 'approved' else '7.25' if status == 'manual_review' else '0'
    return dict(principal=text(principal), **{k: dict(numerator=text(n), denominator=text(d)) for k, (n, d) in pairs.items()},
                risk_points=text(risk), interest_rate=rate, status=status, reason=reason)


def probes():
    epsilon = F('0.000000000001')
    debts = [F(t) + delta for t in ('.36', '.43', '.50') for delta in (-epsilon, 0, epsilon)]
    loans = [F(t) + delta for t in ('.80', '.90', '.97') for delta in (-epsilon, 0, epsilon)]
    reserves = [F(t) + delta for t in ('1', '3') for delta in (-epsilon, 0, epsilon)]
    for i, (dti, ltv, reserve, credit) in enumerate(product(debts, loans, reserves, ('699', '780'))):
        home = F(100000)
        principal = home * ltv
        down = home - principal
        a = application(credit_score=credit, home_price=text(home), down_payment=text(down),
                        available_cash=text(down + reserve * principal * F('.006')),
                        monthly_debt=text(dti * 10000))
        yield dict(id=f'boundary-{i}', input={'application': a}, expected={'decision': expected(a)})
    for i, (credit, bankruptcies, years, late, collections) in enumerate(product(
            ('659', '660', '699', '700', '759', '760'), ('0', '1'), ('1.999', '2'),
            ([], ['1', '1']), ([], ['3']))):
        a = application(credit_score=credit, bankruptcies=bankruptcies, employment_years=years,
                        late_payments=late, collections=collections)
        yield dict(id=f'precedence-{i}', input={'application': a}, expected={'decision': expected(a)})
    for i, income in enumerate(('80000', '90000', '120000', '0.000001')):
        a = application(annual_income=income)
        yield dict(id=f'recurring-{i}', input={'application': a}, expected={'decision': expected(a)})


if __name__ == '__main__':
    rows = list(probes())
    destination = Path('crates/gwt-core/tests/fixtures/underwriting.json')
    destination.write_text(json.dumps(rows, indent=2) + '\n')
    print(f'{len(rows)} independent rational expectations written to {destination}')
