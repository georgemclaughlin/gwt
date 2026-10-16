"""Emit the independent decimal fixture used by the Rust rounding tests."""
from decimal import Decimal, localcontext, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_DOWN, ROUND_FLOOR, ROUND_CEILING
import json

modes={'half_even':ROUND_HALF_EVEN,'half_away_from_zero':ROUND_HALF_UP,'toward_zero':ROUND_DOWN,'floor':ROUND_FLOOR,'ceiling':ROUND_CEILING}
rows=[]
with localcontext() as context:
    context.prec=1600
    for mode,rounding in modes.items():
        for scale in [0,1,2]:
            for numerator in [-11,-5,-1,0,1,5,11]:
                for denominator in [-200,-2,2,3,7,200]:
                    result=(Decimal(numerator)/Decimal(denominator)).quantize(Decimal(1).scaleb(-scale),rounding=rounding)
                    expected='0' if not result else format(result.normalize(),'f')
                    rows.append({'mode':mode,'scale':scale,'numerator':str(numerator),'denominator':str(denominator),'expected':expected})
print(json.dumps({'oracle':'Python decimal at precision 1600; explicit quantize rounding; no host binary floats','cases':rows},indent=2))
