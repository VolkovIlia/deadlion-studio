// See LICENSE file for copyright and license details.
//
// __NAME__ - pick a line interactively
//
// Lines come from stdin, the list is drawn on /dev/tty and the chosen line
// goes to stdout, so __NAME__ sits in any pipeline.

mod config;
mod term;
mod ui;
mod util;

use std::env;
use std::io::{self, BufRead, Write};
use std::process;

use ui::{State, Step};
use util::die;

fn usage() -> ! {
    let _ = writeln!(io::stderr(), "usage: __NAME__ [-v]");
    process::exit(1);
}

/// Accept `-v` or no arguments (`--` alone ends the options); operands and
/// any other option are usage errors.
fn parse_args() {
    let args: Vec<String> = env::args().skip(1).collect();
    let args: Vec<&str> = args.iter().map(String::as_str).collect();
    match args.as_slice() {
        [] | ["--"] => {}
        ["-v"] => {
            // println! would panic on a closed stdout (EPIPE).
            let ok = writeln!(io::stdout(), "__NAME__-{}", env!("CARGO_PKG_VERSION")).is_ok();
            process::exit(if ok { 0 } else { 1 });
        }
        _ => usage(),
    }
}

fn read_items() -> Vec<String> {
    let mut items = Vec::new();
    for line in io::stdin().lock().lines() {
        match line {
            Ok(line) => items.push(line),
            Err(e) => die(&format!("<stdin>: {e}")),
        }
    }
    if items.is_empty() {
        die("no input");
    }
    items
}

/// Run the picker on /dev/tty; Some(line) when one was picked.
fn run(items: Vec<String>, color: bool) -> io::Result<Option<String>> {
    let mut tty = term::open()?;
    let mut state = State::new(items);
    let mut drawn = (0, 0);
    let mut dirty = true;
    while !term::interrupted() {
        let size = tty.size();
        if dirty || size != drawn {
            tty.write(&state.draw(size.0, size.1, color))?;
            drawn = size;
            dirty = false;
        }
        for key in ui::decode(&tty.read(100)?) {
            dirty = true;
            match state.handle(key) {
                Step::Continue => {}
                Step::Pick(line) => return Ok(Some(line)),
                Step::Cancel => return Ok(None),
            }
        }
    }
    Ok(None)
}

fn main() {
    parse_args();
    let items = read_items();
    if env::var("TERM").is_ok_and(|t| t == "dumb") {
        die("TERM=dumb: cannot draw");
    }
    let color = env::var("NO_COLOR").map_or(true, |v| v.is_empty());
    match run(items, color) {
        Ok(Some(line)) => {
            let mut out = io::stdout().lock();
            if let Err(e) = writeln!(out, "{line}").and_then(|_| out.flush()) {
                die(&format!("write error: {e}"));
            }
        }
        Ok(None) => process::exit(1),
        Err(e) => die(&format!("/dev/tty: {e}")),
    }
}
