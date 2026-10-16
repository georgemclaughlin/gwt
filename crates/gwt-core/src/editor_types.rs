//! Declaration provenance for structural types. Equal shapes are not identities.
use crate::{CompiledProgram, program_source::Node, source::Span};

#[derive(Clone, Default)]
pub(crate) enum Origin<'a> {
    Text(&'a str),
    Fields(&'a [Node]),
    OneOf(&'a [Node]),
    List(Box<Origin<'a>>),
    #[default]
    Unknown,
}

impl PartialEq for Origin<'_> {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (Self::Text(a), Self::Text(b)) => a == b,
            (Self::Fields(a), Self::Fields(b)) | (Self::OneOf(a), Self::OneOf(b)) => {
                std::ptr::eq(*a, *b)
            }
            (Self::List(a), Self::List(b)) => a == b,
            (Self::Unknown, Self::Unknown) => true,
            _ => false,
        }
    }
}

pub(crate) struct Origins<'a>(pub &'a CompiledProgram, pub Option<(usize, usize)>);

impl<'a> Origins<'a> {
    pub fn kind_declaration(&self, mut base: &'a str, kind: &str) -> Option<&'a Node> {
        for _ in 0..128 {
            let (_, _, node) = self
                .0
                .type_declarations
                .iter()
                .find(|(name, _, _)| name == base.trim())?;
            if node.text.ends_with(" is one of") {
                return node
                    .children
                    .iter()
                    .find(|node| node.text.strip_suffix(':') == Some(kind));
            }
            base = node.text.strip_prefix("TYPE ")?.split_once(" is ")?.1;
            if let Some((parent, selected)) = base.split_once(" of kind ") {
                if selected != kind {
                    return None;
                }
                base = parent;
            }
        }
        None
    }

    pub fn annotation(&self, site: &Span) -> Origin<'a> {
        let scoped = self.1.map(|(start, end)| &self.0.type_uses[start..end]);
        let uses = scoped
            .filter(|uses| uses.iter().any(|usage| usage.site == *site))
            .unwrap_or(&self.0.type_uses);
        let mut uses = uses.iter().filter(|usage| usage.site == *site);
        let Some(first) = uses.next() else {
            return Origin::Unknown;
        };
        // Use the compiled scenario's annotation range for expanded templates.
        // Do not pick an arbitrary record if an unresolved shared site remains.
        if uses.any(|usage| usage.text != first.text) {
            return Origin::Unknown;
        }
        Origin::Text(&first.text)
    }

    pub fn normalize(&self, mut origin: Origin<'a>) -> Origin<'a> {
        for _ in 0..128 {
            let Origin::Text(text) = origin else {
                return origin;
            };
            let text = text.trim();
            if let Some(inner) = text
                .strip_prefix("optional<")
                .and_then(|s| s.strip_suffix('>'))
            {
                origin = Origin::Text(inner);
            } else if let Some((base, kind)) = text.split_once(" of kind ") {
                return self
                    .kind_declaration(base, kind)
                    .map_or(Origin::Unknown, |node| Origin::Fields(&node.children));
            } else if let Some((_, _, node)) = self
                .0
                .type_declarations
                .iter()
                .find(|(name, _, _)| name == text)
            {
                if node.text.starts_with("RECORD ") {
                    if node.text.ends_with(" is one of") {
                        return Origin::OneOf(&node.children);
                    }
                    return Origin::Fields(&node.children);
                }
                origin = Origin::Text(node.text.split_once(" is ").expect("checked alias").1);
            } else {
                return Origin::Text(text);
            }
        }
        Origin::Unknown
    }

    pub fn element(&self, origin: Origin<'a>) -> Origin<'a> {
        match self.normalize(origin) {
            Origin::List(element) => *element,
            Origin::Text(text) => text
                .strip_prefix("list<")
                .and_then(|s| s.strip_suffix('>'))
                .map_or(Origin::Unknown, Origin::Text),
            _ => Origin::Unknown,
        }
    }

    pub fn field(
        &self,
        origin: Origin<'a>,
        name: &str,
        kinds: Option<&Vec<String>>,
    ) -> Option<(Origin<'a>, Span)> {
        let fields = match self.normalize(origin) {
            Origin::Fields(fields) => fields,
            Origin::OneOf(variants) => {
                let [kind] = kinds?.as_slice() else {
                    return None;
                };
                &variants
                    .iter()
                    .find(|node| node.text.strip_suffix(':') == Some(kind))?
                    .children
            }
            _ => return None,
        };
        for node in fields {
            let (field, ty) = node.text.split_once(':').expect("checked field");
            if field.trim() == name {
                let span = node.span.within(&node.text, 0, field.trim_end().len());
                let origin = if ty.trim().is_empty() {
                    Origin::Fields(&node.children)
                } else {
                    Origin::Text(ty.trim())
                };
                return Some((origin, span));
            }
        }
        None
    }
}

/// The inner type token in a compiler-recorded annotation; quoted unions are
/// left intact and can never accidentally match a declaration name.
pub(crate) fn type_token(text: &str, span: &Span) -> (String, Span) {
    let mut token = text.trim();
    loop {
        let inner = ["optional<", "list<"]
            .iter()
            .find_map(|prefix| token.strip_prefix(prefix).and_then(|s| s.strip_suffix('>')));
        match inner {
            Some(inner) => token = inner.trim(),
            None => break,
        }
    }
    if let Some((base, _)) = token.split_once(" of kind ") {
        token = base;
    }
    let start = token.as_ptr() as usize - text.as_ptr() as usize;
    // EXAMPLES mapping may cover a whole original line or a table cell rather
    // than the substituted spelling. Preserve that mapped span in that case.
    let token_span = if span.end - span.start == text.len() {
        span.within(text, start, start + token.len())
    } else {
        span.clone()
    };
    (token.into(), token_span)
}

pub(crate) fn kind_token<'a>(text: &'a str, span: &Span) -> Option<(&'a str, &'a str, Span)> {
    let mut token = text.trim();
    loop {
        let inner = ["optional<", "list<"]
            .iter()
            .find_map(|prefix| token.strip_prefix(prefix).and_then(|s| s.strip_suffix('>')));
        match inner {
            Some(inner) => token = inner.trim(),
            None => break,
        }
    }
    let (base, kind) = token.split_once(" of kind ")?;
    let start = kind.as_ptr() as usize - text.as_ptr() as usize;
    Some((base, kind, span.within(text, start, start + kind.len())))
}
