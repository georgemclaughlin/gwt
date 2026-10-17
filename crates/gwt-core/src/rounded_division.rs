//! Exact rational division with an explicit, source-selected rounding policy.
use crate::{
    source::{Diagnostic, Result, Span},
    value::{Type, Value, checked_numeric},
};
use num_bigint::BigInt;
use num_rational::BigRational;
use num_traits::{One, Signed, Zero};

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
    let negative = scaled.is_negative();
    let n = scaled.numer().abs();
    let d = scaled.denom();
    let mut whole = &n / d;
    let remainder = &n % d;
    let increment = match mode {
        Rounding::TowardZero => false,
        Rounding::Floor => negative && !remainder.is_zero(),
        Rounding::Ceiling => !negative && !remainder.is_zero(),
        Rounding::HalfAwayFromZero => &remainder * 2 >= *d,
        Rounding::HalfEven => {
            &remainder * 2 > *d || (&remainder * 2 == *d && !(&whole % 2_u8).is_zero())
        }
    };
    if increment {
        whole += BigInt::one();
    }
    if negative {
        whole = -whole;
    }
    checked_numeric(BigRational::new(whole, factor), &Type::Decimal, span)
}
