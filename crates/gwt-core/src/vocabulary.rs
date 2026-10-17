//! Shared spelling inventory. Semantic parsing remains independently implemented.
use serde::Deserialize;
use std::{collections::BTreeMap, sync::LazyLock};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Vocabulary {
    structural: BTreeMap<String, Vec<String>>,
    actions: Vec<String>,
    primitive_types: Vec<String>,
    literals: Vec<String>,
    expression_words: Vec<String>,
    reserved_behavior_heads: Vec<String>,
}

static WORDS: LazyLock<Vocabulary> = LazyLock::new(|| {
    serde_json::from_str(include_str!("vocabulary.json")).expect("checked native vocabulary")
});

pub(crate) fn primitive_types() -> &'static [String] {
    &WORDS.primitive_types
}

pub(crate) fn reserved_behavior(word: &str) -> bool {
    WORDS.reserved_behavior_heads.iter().any(|w| w == word)
}

pub(crate) fn action(word: &str) -> bool {
    WORDS.actions.iter().any(|w| w == word)
}

pub(crate) fn statement_head(word: &str) -> bool {
    action(word) || WORDS.structural["statement"].iter().any(|w| w == word)
}

pub(crate) fn format_head(word: &str) -> bool {
    action(word) || WORDS.structural.values().flatten().any(|w| w == word)
}

pub(crate) enum Context {
    Statement,
    Step,
    Literal,
    Operator,
}

/// Call only after ordinary resolution fails. Never repair or reinterpret source.
pub(crate) fn hint(message: String, word: &str, context: Context) -> String {
    let words: Vec<&String> = match context {
        Context::Statement => WORDS.structural["statement"]
            .iter()
            .chain(&WORDS.actions)
            .collect(),
        Context::Step => WORDS.structural["step"]
            .iter()
            .chain(&WORDS.structural["declaration"])
            .collect(),
        Context::Literal => WORDS.literals.iter().collect(),
        Context::Operator => WORDS.expression_words.iter().collect(),
    };
    match words
        .into_iter()
        .find(|candidate| candidate.as_str() != word && candidate.eq_ignore_ascii_case(word))
    {
        Some(spelling) => {
            format!("{message}; GWT syntax is case-sensitive: did you mean '{spelling}'?")
        }
        None => message,
    }
}
