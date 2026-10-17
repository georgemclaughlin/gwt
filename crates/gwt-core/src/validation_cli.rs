use gwt_core::{ValidationOptions, render_validation_html, validate_file, validate_file_document};
use serde_json::Value;
use std::path::Path;

pub fn run(args: &[String]) -> Result<(bool, Value), Box<dyn std::error::Error>> {
    let usage = "usage: gwt validate FILE.gwt [--import-root DIRECTORY] [--limits FILE.json] [--allow-no-scenarios] [--html NEW_REPORT.html]";
    let Some(entry) = args.first().filter(|entry| !entry.starts_with("--")) else {
        return Err(usage.into());
    };
    let mut root = None;
    let mut html = None;
    let mut limits_path = None;
    let mut options = ValidationOptions::default();
    let mut arguments = args[1..].iter();
    while let Some(argument) = arguments.next() {
        match argument.as_str() {
            "--allow-no-scenarios" if !options.allow_no_scenarios => {
                options.allow_no_scenarios = true
            }
            "--import-root" if root.is_none() => {
                root = Some(
                    arguments
                        .next()
                        .filter(|value| !value.starts_with("--"))
                        .ok_or(usage)?,
                );
            }
            "--html" if html.is_none() => {
                html = Some(
                    arguments
                        .next()
                        .filter(|value| !value.starts_with("--"))
                        .ok_or(usage)?,
                );
            }
            "--limits" if limits_path.is_none() => {
                limits_path = Some(
                    arguments
                        .next()
                        .filter(|value| !value.starts_with("--"))
                        .ok_or(usage)?,
                );
            }
            _ => return Err(usage.into()),
        }
    }
    if let Some(path) = limits_path {
        options.limits = super::limits_cli::read(path)?;
    }
    let report = if let Some(path) = html {
        let document = validate_file_document(Path::new(entry), root.map(Path::new), options);
        super::migration_cli::write_new(path, &render_validation_html(&document)?)?;
        document.into_report()
    } else {
        validate_file(Path::new(entry), root.map(Path::new), options)
    };
    Ok((report.ok, serde_json::to_value(report)?))
}
