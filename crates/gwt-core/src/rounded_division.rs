//! Exact rational division with an explicit, source-selected rounding policy.
use crate::{
    source::{Diagnostic, Result, Span},
    value::{Type, Value, checked_numeric},
};
use num_bigint::BigInt;
use num_integer::Integer;
use num_rational::{BigRational, Ratio};
use num_traits::{Signed, Zero};
use std::cmp::Ordering;

#[derive(Clone, Copy, Debug)]
pub(crate) enum Rounding {
    HalfEven,
    HalfAwayFromZero,
    TowardZero,
    Floor,
    Ceiling,
}
impl Rounding {
    pub fn parse(text: &str) -> Option<Self> {
        Some(match text {
            "half_even" => Self::HalfEven,
            "half_away_from_zero" => Self::HalfAwayFromZero,
            "toward_zero" => Self::TowardZero,
            "floor" => Self::Floor,
            "ceiling" => Self::Ceiling,
            _ => return None,
        })
    }
    pub fn name(self) -> &'static str {
        match self {
            Self::HalfEven => "half_even",
            Self::HalfAwayFromZero => "half_away_from_zero",
            Self::TowardZero => "toward_zero",
            Self::Floor => "floor",
            Self::Ceiling => "ceiling",
        }
    }
}

pub(crate) fn divide(
    left: &Value,
    right: &Value,
    scale: u32,
    mode: Rounding,
    span: &Span,
) -> Result<Value> {
    let numerator = left.rational().expect("checked numeric operand");
    let denominator = right.rational().expect("checked numeric operand");
    if denominator.is_zero() {
        return Err(Diagnostic::new(
            "division_by_zero",
            "division by zero",
            span,
        ));
    }
    let factor = BigInt::from(10).pow(scale);
    let scaled = numerator / denominator * BigRational::from_integer(factor.clone());
    let whole = round_scaled(&scaled, mode);
    checked_numeric(BigRational::new(whole, factor), &Type::Decimal, span)
}

// Production uses BigInt. The midpoint proof uses i16, which fits every
// intermediate for its signed 8-bit lower neighbors.
fn round_scaled<T: Integer + Signed + Clone>(scaled: &Ratio<T>, mode: Rounding) -> T {
    let negative = scaled.is_negative();
    let d = scaled.denom();
    let (whole, remainder) = scaled.numer().abs().div_rem(d);
    let increment = match mode {
        Rounding::TowardZero => false,
        Rounding::Floor => negative && !remainder.is_zero(),
        Rounding::Ceiling => !negative && !remainder.is_zero(),
        Rounding::HalfAwayFromZero | Rounding::HalfEven => {
            let twice_remainder = remainder.clone() + remainder;
            match twice_remainder.cmp(d) {
                Ordering::Less => false,
                Ordering::Equal => matches!(mode, Rounding::HalfAwayFromZero) || whole.is_odd(),
                Ordering::Greater => true,
            }
        }
    };
    let rounded = if increment { whole + T::one() } else { whole };
    if negative { -rounded } else { rounded }
}

#[cfg(any(kani, test))]
mod midpoint_proofs {
    use super::{Integer, Ratio, Rounding, Signed, round_scaled};

    fn check_midpoint<T: Integer + Signed + Clone + From<i16>>(k: i8) {
        let lower = i16::from(k);
        let upper = lower + 1;
        // An odd numerator over two is already in lowest terms.
        let midpoint = Ratio::new_raw(T::from(2 * lower + 1), T::from(2));
        let rounded = round_scaled(&midpoint, Rounding::HalfEven);
        let expected = if lower % 2 == 0 { lower } else { upper };
        assert!(
            rounded == T::from(expected),
            "wrong even neighbor for k={k}"
        );
    }

    #[cfg(kani)]
    #[kani::proof]
    fn half_even_midpoints_select_even_neighbor() {
        let k: i8 = kani::any();
        check_midpoint::<i16>(k);
        kani::cover!(k == i8::MIN, "lowest midpoint");
        kani::cover!(k == i8::MAX, "highest midpoint rounds to 128");
    }

    #[cfg(test)]
    #[test]
    fn bigint_half_even_selects_even_neighbor_for_every_i8_midpoint() {
        for k in i8::MIN..=i8::MAX {
            check_midpoint::<num_bigint::BigInt>(k);
        }
    }
}
