// See LICENSE file for copyright and license details.

use std::io::{self, Write};
use std::process;

/// Print `__NAME__: MSG` on stderr and exit 1. A failed stderr write (hung-up
/// terminal, closed pipe) is ignored: eprintln! would panic there, and with
/// panic = "abort" that is a core dump instead of exit 1.
pub fn die(msg: &str) -> ! {
    let _ = writeln!(io::stderr(), "__NAME__: {msg}");
    process::exit(1);
}
