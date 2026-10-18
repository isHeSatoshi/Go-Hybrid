//! const_overflow.rs — regression for issue #148: a constant initializer
//! outside a declared fixed-width integer type used to pass `hyb check`
//! (0 diagnostics) and then fail `go vet` / `go build` with
//! `cannot use N as T value (overflows)`.

use hy_check::{check_file, Verdict};
use hy_diag::Severity;
use hy_syntax::parse_file;

fn check(src: &str) -> hy_check::CheckResult {
    let path = "inline.hy";
    let ast = parse_file(path, src)
        .unwrap_or_else(|diags| panic!("must parse (parser contract): {:?}", diags));
    check_file(&ast)
}

fn error_codes(r: &hy_check::CheckResult) -> Vec<String> {
    r.diagnostics
        .iter()
        .filter(|d| d.severity == Severity::Error)
        .map(|d| d.code.clone())
        .collect()
}

const OVERFLOW_INT8: &str = "\
fn main() {
    var n int8 = 300
    fmt.println(\"{n}\")
}
";

const OVERFLOW_UINT8: &str = "\
fn main() {
    var n uint8 = 256
    fmt.println(\"{n}\")
}
";

const OVERFLOW_BYTE_HEX: &str = "\
fn main() {
    var n byte = 0x100
    fmt.println(\"{n}\")
}
";

const OVERFLOW_NEG_INT8: &str = "\
fn main() {
    var n int8 = -129
    fmt.println(\"{n}\")
}
";

const OVERFLOW_FILE_CONST: &str = "\
const n int8 = 300

fn main() {
    fmt.println(\"{n}\")
}
";

const FITS_INT8: &str = "\
fn main() {
    var n int8 = 127
    var m int8 = -128
    fmt.println(\"{n} {m}\")
}
";

const FITS_BYTE: &str = "\
fn main() {
    var n byte = 255
    fmt.println(\"{n}\")
}
";

const VARIABLE_OPERAND_OK: &str = "\
fn main() {
    x := 300
    y := byte(x)
    fmt.println(\"{y}\")
}
";

const PAREN_OVERFLOW: &str = "\
fn main() {
    var n int8 = (300)
    fmt.println(\"{n}\")
}
";

#[test]
fn int8_constant_300_is_rejected() {
    let r = check(OVERFLOW_INT8);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for var n int8 = 300, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn int8_constant_underscore_3_00_is_rejected() {
    let r = check("fn main() { var n int8 = 3_00\n fmt.println(\"{n}\") }");
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for var n int8 = 3_00, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn int8_legacy_octal_0177_fits_in_go_must_accept() {
    let r = check("fn main() { var n int8 = 0177\n fmt.println(\"{n}\") }");
    let cs = error_codes(&r);
    assert!(
        !cs.iter().any(|c| c == "HYB-E6002"),
        "0177 is 127 in Go (fits in int8), but got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Accept);
}

#[test]
fn int8_legacy_octal_0200_overflows_must_reject() {
    let r = check("fn main() { var n int8 = 0200\n fmt.println(\"{n}\") }");
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "0200 is 128 in Go (overflows int8), expected HYB-E6002, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn byte_legacy_octal_0377_fits_must_accept() {
    let r = check("fn main() { var n byte = 0377\n fmt.println(\"{n}\") }");
    let cs = error_codes(&r);
    assert!(
        !cs.iter().any(|c| c == "HYB-E6002"),
        "0377 is 255 in Go (fits in byte), but got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Accept);
}

#[test]
fn byte_legacy_octal_0400_overflows_must_reject() {
    let r = check("fn main() { var n byte = 0400\n fmt.println(\"{n}\") }");
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "0400 is 256 in Go (overflows byte), expected HYB-E6002, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn file_const_legacy_octal_fits_must_accept() {
    let r = check("const max_byte byte = 0377\nfn main() { _ = max_byte }");
    let cs = error_codes(&r);
    assert!(
        !cs.iter().any(|c| c == "HYB-E6002"),
        "file-level const 0377 is 255 in Go (fits in byte), but got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Accept);
}

#[test]
fn file_const_legacy_octal_overflows_must_reject() {
    let r = check("const max_byte byte = 0400\nfn main() { _ = max_byte }");
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "file-level const 0400 is 256 in Go (overflows byte), expected HYB-E6002, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn uint8_constant_256_is_rejected() {
    let r = check(OVERFLOW_UINT8);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn byte_hex_0x100_is_rejected() {
    let r = check(OVERFLOW_BYTE_HEX);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for byte = 0x100, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn int8_neg_129_is_rejected() {
    let r = check(OVERFLOW_NEG_INT8);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for -129, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn file_level_const_overflow_is_rejected() {
    let r = check(OVERFLOW_FILE_CONST);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for file-level const, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn paren_wrapped_overflow_is_rejected() {
    let r = check(PAREN_OVERFLOW);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for (300), got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn int8_boundary_values_accept() {
    let r = check(FITS_INT8);
    assert!(
        error_codes(&r).is_empty(),
        "127 / -128 must fit int8, got {:?}",
        error_codes(&r)
    );
    assert_eq!(r.verdict, Verdict::Accept);
}

#[test]
fn byte_255_accepts() {
    let r = check(FITS_BYTE);
    assert!(
        error_codes(&r).is_empty(),
        "255 must fit byte, got {:?}",
        error_codes(&r)
    );
    assert_eq!(r.verdict, Verdict::Accept);
}

#[test]
fn variable_conversion_truncation_still_accepts() {
    // Issue #148 control: conversion from a *variable* is the runtime
    // truncation path (SPEC X4) and must stay accepted.
    let r = check(VARIABLE_OPERAND_OK);
    assert!(
        error_codes(&r).is_empty(),
        "variable conversion must stay clean, got {:?}",
        error_codes(&r)
    );
    assert_eq!(r.verdict, Verdict::Accept);
}

// ---------------------------------------------------------------------------
// W10 (2026-10-17): the E6002 range check is bypassable by a file-level
// `const` alias: `const big = 300; var n int8 = big` passes `hyb check` and
// the emitted Go fails `go build` (`cannot use big (untyped int constant 300)
// as int8 value … (overflows)`). The checker must resolve `const` identifiers
// to their (constant) initializer before folding. A local binding with the
// same name shadows the file-level const and must NOT be resolved.
// ---------------------------------------------------------------------------

const CONST_ALIAS_INT8: &str = "\
const big = 300

fn main() {
    var n int8 = big
    fmt.println(\"{n}\")
}
";

const CONST_ALIAS_WIDER_OK: &str = "\
const big = 300

fn main() {
    var i int32 = big
    fmt.println(\"{i}\")
}
";

const CONST_ALIAS_SHADOWED_OK: &str = "\
const big = 300

fn main() {
    big := int8(1)
    var n int8 = big
    fmt.println(\"{n} {big}\")
}
";

#[test]
fn const_alias_overflow_is_rejected() {
    let r = check(CONST_ALIAS_INT8);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for var n int8 = big (big = 300), got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn const_alias_that_fits_wider_declared_type_accepts() {
    let r = check(CONST_ALIAS_WIDER_OK);
    assert!(
        error_codes(&r).is_empty(),
        "var i int32 = big (big = 300) must stay accepted, got {:?}",
        error_codes(&r)
    );
    assert_eq!(r.verdict, Verdict::Accept);
}

#[test]
fn const_alias_shadowed_by_local_accepts() {
    // The local `big` shadows the file-level `big = 300`; the initializer
    // must not be resolved through the const table.
    let r = check(CONST_ALIAS_SHADOWED_OK);
    assert!(
        error_codes(&r).is_empty(),
        "a local shadowing the const must stay accepted, got {:?}",
        error_codes(&r)
    );
    assert_eq!(r.verdict, Verdict::Accept);
}

const CONST_ALIAS_CHAIN_SHADOWED: &str = "\
const a = 300
const big = a

fn main() {
    a := int8(1)
    var n int8 = big
    fmt.println(\"{n} {a}\")
}
";

#[test]
fn const_alias_chain_with_shadowed_inner_name_is_rejected() {
    // The local `a` shadows the file-level `a` only at the use site; the
    // const's own initializer `big = a` still refers to `const a = 300`.
    let r = check(CONST_ALIAS_CHAIN_SHADOWED);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for big = a = 300 used as int8, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn assign_overflow_int8_is_rejected() {
    let src = "\
fn main() {
    var n int8 = 0
    n = 300
    fmt.println(\"{n}\")
}
";
    let r = check(src);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for n = 300, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn compound_assign_overflow_int8_is_rejected() {
    let src = "\
fn main() {
    var n int8 = 0
    n += 300
    fmt.println(\"{n}\")
}
";
    let r = check(src);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for n += 300, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn array_index_assign_overflow_is_rejected() {
    let src = "\
fn main() {
    var a [2]int8
    a[0] = 300
    fmt.println(\"{a}\")
}
";
    let r = check(src);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for a[0] = 300, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn slice_index_assign_overflow_is_rejected() {
    let src = "\
fn main() {
    var s []int8
    s[0] = 300
    fmt.println(\"{s}\")
}
";
    let r = check(src);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for s[0] = 300, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}

#[test]
fn map_value_assign_overflow_is_rejected() {
    let src = "\
fn main() {
    var m map[string]int8
    m[\"k\"] = 300
    fmt.println(\"{m}\")
}
";
    let r = check(src);
    let cs = error_codes(&r);
    assert!(
        cs.iter().any(|c| c == "HYB-E6002"),
        "expected HYB-E6002 for m[\"k\"] = 300, got {:?}",
        cs
    );
    assert_eq!(r.verdict, Verdict::Reject);
}
