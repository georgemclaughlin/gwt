use super::{Axes, Axis, unsupported};
use crate::source::{Result, Span};
use crate::value::{MAX_DIGITS, Value};
use num_bigint::BigInt;
use serde_json::{Value as Json, json};

// Half-open intervals allow adjacent bands to share a boundary without sharing a value.
#[derive(Clone, Debug)]
struct Band<T> {
    start: T,
    end: T,
}

impl<T: Ord + Clone> Band<T> {
    fn split(self, cut: T) -> (Self, Option<Self>) {
        if cut <= self.start || cut >= self.end {
            return (self, None);
        }
        (
            Self {
                start: self.start,
                end: cut.clone(),
            },
            Some(Self {
                start: cut,
                end: self.end,
            }),
        )
    }
}

#[derive(Clone)]
struct Choice {
    condition: Json,
    near: Json,
    far: Json,
    longest: Json,
}

impl Choice {
    fn integer(field: &str, band: Band<BigInt>, first: &BigInt, end: &BigInt) -> Self {
        let high: BigInt = &band.end - 1;
        let lo_open = &band.start == first;
        let hi_open = &band.end == end;
        let low_json = Value::Integer(band.start.clone()).json();
        let high_json = Value::Integer(high.clone()).json();
        // The widest signed decimal spelling maximizes this input's evidence bytes.
        let longest = if band.start.to_string().len() >= high.to_string().len() {
            low_json.clone()
        } else {
            high_json.clone()
        };
        let (near, far) = match (lo_open, hi_open) {
            (true, true) => (json!(0), json!(0)),
            (true, false) => (high_json.clone(), high_json),
            (false, true) => (low_json.clone(), low_json),
            _ => (low_json, high_json),
        };
        let min = (!lo_open).then(|| band.start.to_string());
        let max = (!hi_open).then(|| high.to_string());
        Self {
            condition: json!({"field":field, "min":min, "max":max}),
            near,
            far,
            longest,
        }
    }
}

pub(super) struct Partition {
    axes: Vec<(Vec<String>, Vec<Choice>)>,
    pub count: usize,
}

pub(super) struct Cell {
    pub conditions: Vec<Json>,
    pub witness: Json,
    pub edge: Json,
    pub longest: Json,
}

impl Partition {
    pub fn new(axes: Axes, span: &Span) -> Result<Self> {
        // Both signs admit MAX_DIGITS decimal digits. One past the maximum is
        // an internal sentinel and is never sent to the interpreter.
        let end = BigInt::from(10).pow(MAX_DIGITS as u32);
        let first: BigInt = 1 - &end;
        let mut count = 1usize;
        let mut dimensions = Vec::new();
        for (path, axis) in axes {
            let field = path.join(".");
            let choices = match axis {
                Axis::Boolean => [false, true]
                    .into_iter()
                    .map(|b| Choice {
                        condition: json!({"field":field,"equals":b}),
                        near: json!(b),
                        far: json!(b),
                        longest: json!(b),
                    })
                    .collect::<Vec<_>>(),
                Axis::Integer(cuts) => {
                    let mut tail = Band {
                        start: first.clone(),
                        end: end.clone(),
                    };
                    let mut bands = vec![];
                    for cut in cuts {
                        let (left, right) = tail.split(cut);
                        if let Some(right) = right {
                            bands.push(left);
                            tail = right;
                        } else {
                            tail = left;
                        }
                    }
                    bands.push(tail);
                    bands
                        .into_iter()
                        .map(|band| Choice::integer(&field, band, &first, &end))
                        .collect()
                }
            };
            count = count
                .checked_mul(choices.len())
                .filter(|n| *n <= super::MAX_REGIONS)
                .ok_or_else(|| unsupported(span, "partition exceeds 1024 regions"))?;
            dimensions.push((path, choices));
        }
        Ok(Self {
            axes: dimensions,
            count,
        })
    }

    pub fn cell(&self, mut index: usize) -> Cell {
        let mut cell = Cell {
            conditions: vec![],
            witness: json!({}),
            edge: json!({}),
            longest: json!({}),
        };
        for (path, choices) in &self.axes {
            let choice = &choices[index % choices.len()];
            index /= choices.len();
            cell.conditions.push(choice.condition.clone());
            for (input, value) in [
                (&mut cell.witness, &choice.near),
                (&mut cell.edge, &choice.far),
                (&mut cell.longest, &choice.longest),
            ] {
                let mut field = input;
                for name in path {
                    field = &mut field[name];
                }
                *field = value.clone();
            }
        }
        cell
    }
}

#[cfg(kani)]
mod proofs {
    use super::Band;

    #[kani::proof]
    fn splitting_a_band_preserves_unique_membership() {
        let (start, end, cut, x): (i16, i16, i16, i16) = kani::any();
        kani::assume(start < end);
        let (left, right) = Band { start, end }.split(cut);
        let contains = |band: &Band<i16>| band.start <= x && x < band.end;
        assert!(left.start < left.end);
        assert!(right.as_ref().is_none_or(|b| b.start < b.end));
        let memberships =
            u8::from(contains(&left)) + u8::from(right.as_ref().is_some_and(contains));
        assert_eq!(memberships, u8::from(start <= x && x < end));
        kani::cover!(
            right.is_some() && x == cut,
            "cut point belongs to the right band"
        );
    }
}
