use std::collections::BTreeMap;

/// Parse value-bearing flags without accepting duplicates or dropping a trailing flag.
/// Commands retain their own option vocabulary, required fields, and diagnostics.
pub(crate) fn paired<'a>(
    args: &'a [String],
    allowed: impl Fn(&str) -> bool,
    error: &'static str,
) -> Result<BTreeMap<&'a str, &'a str>, &'static str> {
    if args.len() % 2 != 0 {
        return Err(error);
    }
    let mut options = BTreeMap::new();
    for pair in args.chunks_exact(2) {
        if !allowed(&pair[0]) || options.insert(pair[0].as_str(), pair[1].as_str()).is_some() {
            return Err(error);
        }
    }
    Ok(options)
}
