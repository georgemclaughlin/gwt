use gwt_core::{EditorQuery, EditorSymbol, check_editor_query};
use std::{
    collections::BTreeMap,
    fs,
    sync::atomic::{AtomicUsize, Ordering},
};
static NEXT: AtomicUsize = AtomicUsize::new(0);

fn symbols(main: &str, types: &str, path: &str, offset: usize) -> Vec<EditorSymbol> {
    let root = std::env::temp_dir().join(format!(
        "gwt-editor-types-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir(&root).unwrap();
    let report = check_editor_query(
        &root.join("main.gwt"),
        Some(&root),
        &BTreeMap::from([
            ("main.gwt".into(), main.into()),
            ("types.gwt".into(), types.into()),
        ]),
        Some(&EditorQuery {
            path: path.into(),
            byte_offset: offset,
        }),
    );
    fs::remove_dir(&root).unwrap();
    assert!(report.ok, "{:?}", report.diagnostic);
    report.navigation.unwrap().symbols
}

const TYPES: &str = "TYPE Money is integer\nRECORD Line\n  price: Money\n  metadata:\n    code: text\nTYPE Item is Line\nTYPE Items is list<Item>\nTYPE MaybeItem is optional<Item>\nRECORD Other\n  price: integer\n";

#[test]
fn typed_local_records_navigate_imported_types_initializers_and_result_fields() {
    let types = "RECORD Facts\n  amount: decimal\nTYPE Quote is Facts\n";
    let main = "# café 😀\r\nUSE \"types.gwt\"\r\nWHEN quote <facts>\r\n  GIVEN facts is Facts\r\n  LET result be Quote:\r\n    amount: facts.amount\r\n  print result.amount\r\n";
    let annotation = symbols(main, types, "main.gwt", main.find("Quote:").unwrap());
    assert_eq!(annotation[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        annotation[0].definition.as_ref().unwrap().start,
        types.find("TYPE Quote").unwrap()
    );
    for path in ["facts.amount", "result.amount"] {
        let field = symbols(
            main,
            types,
            "main.gwt",
            main.find(path).unwrap() + path.find('.').unwrap() + 1,
        );
        assert_eq!(field[0].kind, "field");
        assert_eq!(field[0].definition.as_ref().unwrap().file, "types.gwt");
        assert_eq!(
            field[0].definition.as_ref().unwrap().start,
            types.find("amount:").unwrap()
        );
    }
    let local = symbols(
        main,
        types,
        "main.gwt",
        main.find("print result").unwrap() + 6,
    );
    assert_eq!(local[0].kind, "binding");
    assert_eq!(
        local[0].definition.as_ref().unwrap().start,
        main.find("result be").unwrap()
    );
}

#[test]
fn value_dispatch_navigates_subject_fields_branch_locals_and_calls() {
    let types =
        "RECORD Facts\n  status: text\nWHEN echo <value>\n  GIVEN value is text\n  print value\n";
    let main = "# café 😀\r\nUSE \"types.gwt\"\r\nWHEN inspect <facts>\r\n  GIVEN facts is Facts\r\n  DEPENDING ON facts.status\r\n    WHEN the value is \"ready\"\r\n      LET label be \"accepted\"\r\n      echo label\r\n    ELSE\r\n      echo facts.status\r\n";
    let field = symbols(
        main,
        types,
        "main.gwt",
        main.find("facts.status").unwrap() + 6,
    );
    assert_eq!(field[0].kind, "field");
    assert_eq!(field[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        field[0].definition.as_ref().unwrap().start,
        types.find("status:").unwrap()
    );
    let local = symbols(
        main,
        types,
        "main.gwt",
        main.find("echo label").unwrap() + 5,
    );
    assert_eq!(local[0].kind, "binding");
    assert_eq!(
        local[0].definition.as_ref().unwrap().start,
        main.find("LET label").unwrap() + 4
    );
    let call = symbols(main, types, "main.gwt", main.rfind("echo facts").unwrap());
    assert_eq!(call[0].kind, "behavior");
    assert_eq!(call[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        call[0].definition.as_ref().unwrap().start,
        types.find("WHEN echo").unwrap()
    );
}

#[test]
fn presence_refined_paths_keep_their_optional_record_field_origins() {
    let types = "RECORD Item\n  amount: integer\nRECORD Facts\n  item: optional<Item>\n";
    let main = "# café 😀\r\nUSE \"types.gwt\"\r\nWHEN inspect <facts>\r\n  GIVEN facts is Facts\r\n  IF facts.item is present\r\n    print facts.item.amount\r\n";
    let field = symbols(
        main,
        types,
        "main.gwt",
        main.find("item.amount").unwrap() + 5,
    );
    assert_eq!(field[0].kind, "field");
    assert_eq!(field[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        field[0].definition.as_ref().unwrap().start,
        types.find("amount:").unwrap()
    );
}

#[test]
fn kind_contracts_navigate_to_the_selected_declaration_and_payload_fields() {
    let types = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    address: text\nTYPE Recipient is Contact\nTYPE Email is Recipient of kind email\nTYPE Alias is Email\n";
    let main = "# café 😀\r\nUSE \"types.gwt\"\r\nWHEN inspect <contact>\r\n  GIVEN contact is Alias\r\n  print contact.address\r\n";
    let field = symbols(
        main,
        types,
        "main.gwt",
        main.find("contact.address").unwrap() + 8,
    );
    assert_eq!(field[0].kind, "field");
    assert_eq!(field[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        field[0].definition.as_ref().unwrap().start,
        types.find("address:").unwrap()
    );
    let base = symbols(
        main,
        types,
        "types.gwt",
        types.find("Recipient of kind").unwrap(),
    );
    assert_eq!(
        base[0].definition.as_ref().unwrap().start,
        types.find("TYPE Recipient").unwrap()
    );
    let tag = symbols(
        main,
        types,
        "types.gwt",
        types.find("of kind email").unwrap() + 8,
    );
    assert_eq!(tag[0].kind, "kind");
    assert_eq!(
        tag[0].definition.as_ref().unwrap().start,
        types.find("email:").unwrap()
    );
    let phone_main = main.replace("contact is Alias", "contact is Contact of kind phone");
    let field = symbols(
        &phone_main,
        types,
        "main.gwt",
        phone_main.find("contact.address").unwrap() + 8,
    );
    assert_eq!(
        field[0].definition.as_ref().unwrap().start,
        types.rfind("address:").unwrap()
    );
}

#[test]
fn one_of_types_keep_declarations_without_inventing_a_common_field_origin() {
    let types = "RECORD Contact is one of\n  email:\n    label: text\n    address: text\n  phone:\n    label: text\n    number: text\nTYPE Recipient is Contact\n";
    let main = "# 😀 café\r\nUSE \"types.gwt\"\r\nWHEN inspect <contact>\r\n  GIVEN contact is Recipient\r\n  print contact.kind\r\n  print contact.label\r\n";
    let alias = symbols(main, types, "main.gwt", main.find("Recipient").unwrap());
    assert_eq!(alias[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        alias[0].definition.as_ref().unwrap().start,
        types.find("TYPE Recipient").unwrap()
    );
    let declaration = symbols(main, types, "types.gwt", types.find("address:").unwrap());
    assert_eq!(declaration[0].kind, "field");
    assert_eq!(
        declaration[0].definition.as_ref().unwrap().start,
        types.find("address:").unwrap()
    );
    for field in ["kind", "label"] {
        let path = format!("contact.{field}");
        let use_site = symbols(main, types, "main.gwt", main.find(&path).unwrap() + 8);
        assert_eq!(use_site[0].kind, "binding");
        assert_eq!(use_site[0].definition.as_ref().unwrap().file, "main.gwt");
        assert_eq!(
            use_site[0].definition.as_ref().unwrap().start,
            main.find("contact is").unwrap()
        );
    }
}

#[test]
fn typed_setup_tables_retain_item_origins_and_cell_binding_navigation() {
    let types = "RECORD Item\n  price: integer\nRECORD Box\n  items: list<Item>\n";
    let main = "USE \"types.gwt\"\nGIVEN seed is 4\nGIVEN items are Item\n  | price |\n  | seed |\nGIVEN box is Box\n  items: items\nGIVEN box.items are Item\n  | price |\n  | seed + 1 |\nGIVEN total is 0\nWHEN sum row.price in items into total\nTHEN total == seed\n";
    let item = symbols(main, types, "main.gwt", main.find("are Item").unwrap() + 4);
    assert_eq!(item[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        item[0].definition.as_ref().unwrap().start,
        types.find("RECORD Item").unwrap()
    );
    let field = symbols(main, types, "main.gwt", main.find("row.price").unwrap() + 4);
    assert_eq!(
        field[0].definition.as_ref().unwrap().start,
        types.find("price:").unwrap()
    );
    assert_eq!(field[0].definition.as_ref().unwrap().file, "types.gwt");
    let cell = symbols(main, types, "main.gwt", main.find("| seed +").unwrap() + 2);
    assert_eq!(
        cell[0].definition.as_ref().unwrap().start,
        main.find("seed is").unwrap()
    );
    let target = symbols(
        main,
        types,
        "main.gwt",
        main.find("box.items are").unwrap() + 4,
    );
    assert_eq!(
        target[0].definition.as_ref().unwrap().start,
        types.find("items:").unwrap()
    );
}

#[test]
fn named_type_references_follow_imports_aliases_and_nested_containers() {
    let main =
        "USE \"types.gwt\"\nWHEN examine <value>\n  GIVEN value is optional<list<Item>>\n  PASS\n";
    let reference = symbols(
        main,
        TYPES,
        "main.gwt",
        main.find("list<Item>").unwrap() + 5,
    );
    assert_eq!(reference.len(), 1);
    assert_eq!(reference[0].kind, "type");
    assert_eq!(reference[0].span.end - reference[0].span.start, 4);
    assert_eq!(reference[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        reference[0].definition.as_ref().unwrap().start,
        TYPES.find("TYPE Item is").unwrap()
    );
    let alias = symbols(main, TYPES, "types.gwt", TYPES.find("is Line").unwrap() + 3);
    assert_eq!(
        alias[0].definition.as_ref().unwrap().start,
        TYPES.find("RECORD Line").unwrap()
    );
    let field_type = symbols(
        main,
        TYPES,
        "types.gwt",
        TYPES.find("price: Money").unwrap() + 7,
    );
    assert_eq!(field_type[0].definition.as_ref().unwrap().start, 0);
    let field_name = symbols(
        main,
        TYPES,
        "types.gwt",
        TYPES.find("price: Money").unwrap(),
    );
    assert_eq!(field_name[0].kind, "field");
    assert!(field_name[0].label.contains("price: integer"));
}

#[test]
fn equal_record_shapes_do_not_confuse_contracts_copies_or_return_types() {
    let types = "RECORD First\n  price: integer\nRECORD Second\n  price: integer\n";
    let main = "USE \"types.gwt\"\nWHEN copy <item>\n  GIVEN item is First\n  THEN returns Second\n  RETURN item\nWHEN inspect <first> and <second>\n  GIVEN first is First\n  GIVEN second is Second\n  print first.price\n  print second.price\n  LET local be first\n  print local.price\n  LET returned be copy first\n  print returned.price\n";
    for (expression, target) in [
        ("first.price", types.find("price:").unwrap()),
        ("second.price", types.rfind("price:").unwrap()),
        ("local.price", types.find("price:").unwrap()),
        ("returned.price", types.rfind("price:").unwrap()),
    ] {
        let field = symbols(
            main,
            types,
            "main.gwt",
            main.find(expression).unwrap() + expression.find('.').unwrap() + 1,
        );
        assert_eq!(field.len(), 1);
        assert_eq!(field[0].kind, "field");
        assert_eq!(field[0].definition.as_ref().unwrap().file, "types.gwt");
        assert_eq!(field[0].definition.as_ref().unwrap().start, target);
    }
    let returned_type = symbols(
        main,
        types,
        "main.gwt",
        main.find("returns Second").unwrap() + 8,
    );
    assert_eq!(
        returned_type[0].definition.as_ref().unwrap().start,
        types.find("RECORD Second").unwrap()
    );
}

#[test]
fn nested_optional_fields_and_collection_projections_keep_declaration_locations() {
    let main = "USE \"types.gwt\"\nWHEN inspect <value> and <items>\n  GIVEN value is MaybeItem\n  GIVEN items is Items\n  print value is present and value.metadata.code == \"x\"\n  LET total be 0\n  FOR item in items\n    add item.price to total\n  sum row.price in items into total\n";
    for (expression, part, expected) in [
        ("value.metadata.code", "metadata", "metadata:"),
        ("value.metadata.code", "code", "code:"),
        ("item.price", "price", "price:"),
        ("row.price", "price", "price:"),
    ] {
        let offset = main.find(expression).unwrap() + expression.find(part).unwrap();
        let found = symbols(main, TYPES, "main.gwt", offset);
        assert_eq!(found[0].kind, "field");
        assert_eq!(
            found[0].definition.as_ref().unwrap().start,
            TYPES.find(expected).unwrap()
        );
    }
    let root = symbols(
        main,
        TYPES,
        "main.gwt",
        main.find("value.metadata.code").unwrap(),
    );
    assert_eq!(root[0].kind, "binding");
    assert_eq!(
        root[0].definition.as_ref().unwrap().start,
        main.find("GIVEN value").unwrap() + 6
    );
}

#[test]
fn inferred_lists_preserve_one_origin_but_never_choose_between_equal_shapes() {
    let types = "RECORD First\n  price: integer\nRECORD Second\n  price: integer\n";
    let main = "USE \"types.gwt\"\nWHEN inspect <first> and <second>\n  GIVEN first is First\n  GIVEN second is Second\n  LET alike be [first, first]\n  FOR same in alike\n    print same.price\n  LET mixed be [first, second]\n  FOR item in mixed\n    print item.price\n";
    let same = symbols(
        main,
        types,
        "main.gwt",
        main.find("same.price").unwrap() + 5,
    );
    assert_eq!(same[0].kind, "field");
    assert_eq!(
        same[0].definition.as_ref().unwrap().start,
        types.find("price:").unwrap()
    );
    let mixed = symbols(
        main,
        types,
        "main.gwt",
        main.find("item.price").unwrap() + 5,
    );
    assert_eq!(mixed[0].kind, "binding");
    assert_eq!(mixed[0].definition.as_ref().unwrap().file, "main.gwt");
    assert_eq!(
        mixed[0].definition.as_ref().unwrap().start,
        main.find("FOR item").unwrap() + 4
    );
}

#[test]
fn request_output_origins_and_unicode_crlf_type_spans_are_preserved() {
    let types = TYPES.replace('\n', "\r\n");
    let main = "# 😀 café\r\nUSE \"types.gwt\"\r\nREQUEST make\r\n  GIVEN item is Item\r\n    price: 3\r\n    metadata:\r\n      code: \"x\"\r\n  WHEN print item\r\n  OUTPUT item is Item\r\nSCENARIO made\r\nREQUEST make\r\nTHEN item.price == 3\r\n";
    let field = symbols(
        main,
        &types,
        "main.gwt",
        main.find("item.price").unwrap() + 5,
    );
    assert_eq!(field[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        field[0].definition.as_ref().unwrap().start,
        types.find("price:").unwrap()
    );
    let annotation = symbols(
        main,
        &types,
        "main.gwt",
        main.find("GIVEN item is Item").unwrap() + 14,
    );
    assert_eq!(
        annotation[0].span.start,
        main.find("GIVEN item is Item").unwrap() + 14
    );
    assert_eq!(annotation[0].span.end - annotation[0].span.start, 4);
    assert_eq!(annotation[0].definition.as_ref().unwrap().line, 6);
}

#[test]
fn example_type_substitution_and_quoted_type_names_never_guess_a_field() {
    let types = "RECORD First\n  price: integer\nRECORD Second\n  price: integer\nTYPE Label is \"First\"\n";
    let main = "USE \"types.gwt\"\nSCENARIO rows\nGIVEN item is <kind>\n  price: 1\nTHEN item.price == 1\nEXAMPLES\n  | kind |\n  | First |\n  | Second |\n";
    let fields = symbols(
        main,
        types,
        "main.gwt",
        main.find("item.price").unwrap() + 5,
    );
    assert_eq!(fields.len(), 2);
    assert!(
        fields.iter().all(|symbol| symbol.kind == "field"
            && symbol.definition.as_ref().unwrap().file == "types.gwt")
    );
    assert_eq!(
        fields[0].definition.as_ref().unwrap().start,
        types.find("price:").unwrap()
    );
    assert_eq!(
        fields[1].definition.as_ref().unwrap().start,
        types.rfind("price:").unwrap()
    );
    assert_eq!(fields[0].context, "SCENARIO rows example 1");
    assert_eq!(fields[1].context, "SCENARIO rows example 2");
    let table_type = symbols(
        main,
        types,
        "main.gwt",
        main.find("| Second |").unwrap() + 2,
    );
    assert_eq!(table_type[0].kind, "type");
    assert_eq!(
        table_type[0].definition.as_ref().unwrap().start,
        types.find("RECORD Second").unwrap()
    );
    let literal = symbols(main, types, "types.gwt", types.rfind("First").unwrap());
    assert!(
        literal
            .iter()
            .all(|symbol| symbol.definition.as_ref().unwrap().start != 0)
    );
}

#[test]
fn condition_narrowed_payload_hover_resolves_its_selected_declaration() {
    let types = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\nRECORD Facts\n  contact: optional<Contact>\n";
    let main = "# café 😀\r\nUSE \"types.gwt\"\r\nWHEN inspect <facts>\r\n  GIVEN facts is Facts\r\n  IF facts.contact is present and facts.contact.kind == \"email\"\r\n    print facts.contact.address\r\n";
    let payload = symbols(
        main,
        types,
        "main.gwt",
        main.find("contact.address").unwrap() + 8,
    );
    assert_eq!(payload.len(), 1);
    assert_eq!(payload[0].kind, "field");
    assert!(payload[0].label.contains("facts.contact.address: text"));
    assert_eq!(payload[0].definition.as_ref().unwrap().file, "types.gwt");
    assert_eq!(
        payload[0].definition.as_ref().unwrap().start,
        types.find("address:").unwrap()
    );
}

const BRANCH_TYPES: &str = "RECORD Contact is one of\n  email:\n    address: text\n    details:\n      label: text\n  phone:\n    address: text\n    details:\n      label: text\n  pickup:\n    location: text\nTYPE Recipient is Contact\nRECORD Facts\n  contact: optional<Recipient>\n";

#[test]
fn branch_reads_writes_and_copied_payloads_follow_the_selected_kind() {
    let main = "# café 😀\r\nUSE \"types.gwt\"\r\nWHEN inspect <facts>\r\n  GIVEN facts is Facts\r\n  IF facts.contact is present\r\n    DECIDE\r\n      WHEN facts.contact.kind == \"email\"\r\n        set facts.contact.address to \"updated\"\r\n        LET copy be facts.contact.details\r\n        print copy.label\r\n      WHEN facts.contact.kind == \"pickup\"\r\n        print facts.contact.location\r\n      ELSE\r\n        print facts.contact.details.label\r\n";
    for (path, part, definition) in [
        (
            "facts.contact.address",
            "address",
            BRANCH_TYPES.find("address:").unwrap(),
        ),
        (
            "facts.contact.details",
            "details",
            BRANCH_TYPES.find("details:").unwrap(),
        ),
        ("copy.label", "label", BRANCH_TYPES.find("label:").unwrap()),
        (
            "facts.contact.location",
            "location",
            BRANCH_TYPES.find("location:").unwrap(),
        ),
        (
            "facts.contact.details.label",
            "label",
            BRANCH_TYPES.rfind("label:").unwrap(),
        ),
    ] {
        let found = symbols(
            main,
            BRANCH_TYPES,
            "main.gwt",
            main.find(path).unwrap() + path.find(part).unwrap(),
        );
        assert_eq!(found.len(), 1, "{path}");
        assert_eq!(found[0].kind, "field", "{path}: {found:?}");
        assert_eq!(found[0].definition.as_ref().unwrap().file, "types.gwt");
        assert_eq!(
            found[0].definition.as_ref().unwrap().start,
            definition,
            "{path}"
        );
    }
    let root = symbols(
        main,
        BRANCH_TYPES,
        "main.gwt",
        main.find("set facts.contact.address").unwrap() + 4,
    );
    assert_eq!(root[0].kind, "binding");
    assert_eq!(
        root[0].definition.as_ref().unwrap().start,
        main.find("GIVEN facts").unwrap() + 6
    );
}

#[test]
fn short_circuit_and_exhaustive_dispatch_have_their_own_field_origins() {
    let main = "USE \"types.gwt\"\nWHEN inspect <contact>\n  GIVEN contact is Recipient\n  REQUIRE contact.kind != \"email\" or contact.address != \"\"\n  DEPENDING ON contact\n    WHEN the kind is email\n      print contact.address\n    WHEN the kind is pickup\n      print contact.location\n    ELSE\n      set contact.address to \"phone\"\n";
    for (site, offset, target) in [
        (
            "or contact.address",
            11,
            BRANCH_TYPES.find("address:").unwrap(),
        ),
        (
            "print contact.address",
            14,
            BRANCH_TYPES.find("address:").unwrap(),
        ),
        (
            "set contact.address",
            12,
            BRANCH_TYPES.rfind("address:").unwrap(),
        ),
    ] {
        let found = symbols(
            main,
            BRANCH_TYPES,
            "main.gwt",
            main.find(site).unwrap() + offset,
        );
        assert_eq!(found[0].kind, "field", "{site}: {found:?}");
        assert_eq!(
            found[0].definition.as_ref().unwrap().start,
            target,
            "{site}"
        );
    }
}

#[test]
fn narrowed_collection_item_and_copied_one_of_values_keep_nominal_origins() {
    let main = "USE \"types.gwt\"\nWHEN inspect <contacts>\n  GIVEN contacts is list<Recipient>\n  FOR contact in contacts\n    IF contact.kind == \"email\"\n      LET copy be contact\n      LET items be [copy]\n      FOR item in items\n        print item.details.label\n      set copy.address to \"x\"\n";
    for (site, part, target) in [
        (
            "item.details.label",
            "label",
            BRANCH_TYPES.find("label:").unwrap(),
        ),
        (
            "copy.address",
            "address",
            BRANCH_TYPES.find("address:").unwrap(),
        ),
    ] {
        let found = symbols(
            main,
            BRANCH_TYPES,
            "main.gwt",
            main.find(site).unwrap() + site.find(part).unwrap(),
        );
        assert_eq!(found[0].kind, "field");
        assert_eq!(found[0].definition.as_ref().unwrap().file, "types.gwt");
        assert_eq!(found[0].definition.as_ref().unwrap().start, target);
    }
}

#[test]
fn distinct_equal_one_of_records_and_ambiguous_kind_sets_never_share_targets() {
    let types = "RECORD First is one of\n  email:\n    address: text\n  phone:\n    address: text\nRECORD Second is one of\n  email:\n    address: text\n  phone:\n    address: text\n";
    let main = "USE \"types.gwt\"\nWHEN inspect <first> with <second>\n  GIVEN first is First\n  AND second is Second\n  IF first.kind == \"email\"\n    print first.address\n  IF second.kind == \"email\"\n    print second.address\n  print first.address\n  LET mixed be [first, second]\n  FOR item in mixed\n    IF item.kind == \"email\"\n      print item.address\n";
    for (site, target) in [
        ("first.address", types.find("address:").unwrap()),
        (
            "second.address",
            types.find("RECORD Second").unwrap()
                + types[types.find("RECORD Second").unwrap()..]
                    .find("address:")
                    .unwrap(),
        ),
    ] {
        let found = symbols(
            main,
            types,
            "main.gwt",
            main.find(site).unwrap() + site.find('.').unwrap() + 1,
        );
        assert_eq!(found[0].definition.as_ref().unwrap().start, target);
    }
    // Several possible kind declarations and a mixed nominal list both remain
    // ambiguous. Structural equality cannot manufacture declaration identity.
    for offset in [
        main.rfind("first.address").unwrap() + 6,
        main.find("item.address").unwrap() + 5,
    ] {
        let found = symbols(main, types, "main.gwt", offset);
        assert_eq!(found[0].kind, "binding");
        assert_eq!(found[0].definition.as_ref().unwrap().file, "main.gwt");
    }
}

#[test]
fn per_example_kind_proofs_keep_distinct_contexts_at_one_original_source_path() {
    let types =
        "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    address: text\n";
    let main = "# café 😀\r\nUSE \"types.gwt\"\r\nSCENARIO contact <label>\r\nGIVEN contact is Contact\r\n  kind: <kind>\r\n  address: \"x\"\r\nTHEN contact.kind == <kind> and contact.address == \"x\"\r\nEXAMPLES\r\n  | label | kind |\r\n  | email | \"email\" |\r\n  | phone | \"phone\" |\r\n";
    let found = symbols(
        main,
        types,
        "main.gwt",
        main.find("contact.address").unwrap() + 8,
    );
    assert_eq!(found.len(), 2, "{found:?}");
    let targets: std::collections::BTreeSet<_> = found
        .iter()
        .map(|s| s.definition.as_ref().unwrap().start)
        .collect();
    assert_eq!(
        targets,
        [
            types.find("address:").unwrap(),
            types.rfind("address:").unwrap()
        ]
        .into()
    );
    assert!(
        found
            .iter()
            .all(|s| s.kind == "field" && &main[s.span.start..s.span.end] == "address")
    );
    assert_ne!(found[0].context, found[1].context);
}

#[test]
fn nested_one_of_prefixes_resolve_through_each_selected_nominal_declaration() {
    let types = "RECORD First is one of\n  email:\n    address: text\n  phone:\n    number: text\nRECORD Second is one of\n  email:\n    address: text\n  phone:\n    number: text\nRECORD Envelope is one of\n  home:\n    contact: First\n  work:\n    contact: Second\n";
    let main = "USE \"types.gwt\"\nWHEN inspect <envelope>\n  GIVEN envelope is Envelope\n  IF envelope.kind == \"home\" and envelope.contact.kind == \"email\"\n    print envelope.contact.address\n  IF envelope.kind == \"work\" and envelope.contact.kind == \"email\"\n    print envelope.contact.address\n";
    let path = "envelope.contact.address";
    for (position, target, field) in [
        (
            main.find(path).unwrap(),
            types.find("address:").unwrap(),
            types.find("contact:").unwrap(),
        ),
        (
            main.rfind(path).unwrap(),
            types.rfind("address:").unwrap(),
            types.rfind("contact:").unwrap(),
        ),
    ] {
        let found = symbols(
            main,
            types,
            "main.gwt",
            position + path.find("address").unwrap(),
        );
        assert_eq!(found[0].definition.as_ref().unwrap().start, target);
        let parent = symbols(
            main,
            types,
            "main.gwt",
            position + path.find("contact").unwrap(),
        );
        assert_eq!(parent[0].definition.as_ref().unwrap().start, field);
        assert!(parent[0].label.contains("one of { email }"));
    }
}

#[test]
fn sequential_require_proofs_preserve_payload_declarations_and_checked_hover() {
    let types = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    address: text\nRECORD Facts\n  contact: optional<Contact>\n";
    for (kind, target) in [
        ("email", types.find("address:").unwrap()),
        ("phone", types.rfind("address:").unwrap()),
    ] {
        let main = format!(
            "# café 😀\r\nUSE \"types.gwt\"\r\nWHEN inspect <facts>\r\n  GIVEN facts is Facts\r\n  REQUIRE facts.contact is present\r\n  REQUIRE facts.contact.kind == \"{kind}\"\r\n  set facts.contact.address to \"checked\"\r\n  LET copied be facts.contact\r\n  print copied.address\r\n"
        );
        for path in ["facts.contact.address", "copied.address"] {
            let found = symbols(
                &main,
                types,
                "main.gwt",
                main.find(path).unwrap() + path.find("address").unwrap(),
            );
            assert_eq!(found.len(), 1);
            assert_eq!(found[0].kind, "field");
            assert_eq!(found[0].definition.as_ref().unwrap().file, "types.gwt");
            assert_eq!(found[0].definition.as_ref().unwrap().start, target);
            assert!(found[0].label.contains("address: text"));
        }
    }
}

#[test]
fn collection_filter_proofs_navigate_optional_payloads_and_copies_in_both_bodies() {
    let types = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    address: text\nRECORD Row\n  contact: optional<Contact>\n";
    for (kind, target) in [
        ("email", types.find("address:").unwrap()),
        ("phone", types.rfind("address:").unwrap()),
    ] {
        for verb in ["FOR", "FIND"] {
            for (ty, filter, path) in [
                (
                    "list<Row>",
                    format!("row.contact is present and row.contact.kind == \"{kind}\""),
                    "row.contact",
                ),
                (
                    "list<optional<Contact>>",
                    format!("row is present and row.kind == \"{kind}\""),
                    "row",
                ),
            ] {
                let fallback = if verb == "FIND" {
                    "  ELSE\r\n    PASS\r\n"
                } else {
                    ""
                };
                let main = format!(
                    "# café 😀\r\nUSE \"types.gwt\"\r\nWHEN inspect <rows>\r\n  GIVEN rows is {ty}\r\n  {verb} row in rows WHERE {filter}\r\n    set {path}.address to \"checked\"\r\n    LET copied be {path}\r\n    print copied.address\r\n{fallback}"
                );
                for use_path in [format!("{path}.address"), "copied.address".into()] {
                    let found = symbols(
                        &main,
                        types,
                        "main.gwt",
                        main.find(&use_path).unwrap() + use_path.find("address").unwrap(),
                    );
                    assert_eq!(found.len(), 1);
                    assert_eq!(found[0].kind, "field");
                    assert_eq!(found[0].definition.as_ref().unwrap().file, "types.gwt");
                    assert_eq!(found[0].definition.as_ref().unwrap().start, target);
                    assert!(found[0].label.contains("address: text"));
                }
            }
        }
    }
}

#[test]
fn early_return_continuations_preserve_optional_payload_declarations_and_copies() {
    let types = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    address: text\nRECORD Facts\n  contact: optional<Contact>\n";
    for (kind, target) in [
        ("email", types.find("address:").unwrap()),
        ("phone", types.rfind("address:").unwrap()),
    ] {
        let main = format!(
            "# café 😀\r\nUSE \"types.gwt\"\r\nWHEN choose <facts>\r\n  GIVEN facts is Facts\r\n  THEN returns text\r\n  IF facts.contact is absent\r\n    RETURN \"missing\"\r\n  IF facts.contact.kind != \"{kind}\"\r\n    RETURN \"other\"\r\n  LET copied be facts.contact\r\n  print copied.address\r\n  RETURN facts.contact.address\r\n"
        );
        for path in ["facts.contact.address", "copied.address"] {
            let found = symbols(
                &main,
                types,
                "main.gwt",
                main.find(path).unwrap() + path.find("address").unwrap(),
            );
            assert_eq!(found.len(), 1);
            assert_eq!(found[0].kind, "field");
            assert_eq!(found[0].definition.as_ref().unwrap().file, "types.gwt");
            assert_eq!(found[0].definition.as_ref().unwrap().start, target);
            assert!(found[0].label.contains("address: text"));
        }
    }
}
