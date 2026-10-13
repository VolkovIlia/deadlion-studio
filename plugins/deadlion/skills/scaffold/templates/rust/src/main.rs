// See LICENSE file for copyright and license details.
//
// __NAME__ - copy files to standard output

mod config;
mod util;

use std::env;
use std::fs::File;
use std::io::{self, BufWriter, ErrorKind, Read, Write};
use std::process;

use util::die;

fn copy(r: &mut impl Read, w: &mut impl Write) -> io::Result<()> {
    let mut buf = vec![0u8; config::BUFSIZE];
    loop {
        match r.read(&mut buf) {
            Ok(0) => return Ok(()),
            Ok(n) => w.write_all(&buf[..n])?,
            Err(e) if e.kind() == ErrorKind::Interrupted => {}
            Err(e) => return Err(e),
        }
    }
}

fn cat(name: &str, out: &mut impl Write) {
    let res = if name == "-" {
        copy(&mut io::stdin().lock(), out)
    } else {
        File::open(name).and_then(|mut f| copy(&mut f, out))
    };
    if let Err(e) = res {
        die(&format!("{name}: {e}"));
    }
}

fn usage() -> ! {
    let _ = writeln!(io::stderr(), "usage: __NAME__ [-v] [file...]");
    process::exit(1);
}

fn version() -> ! {
    // println! would panic on a closed stdout (EPIPE).
    let ok = writeln!(io::stdout(), "__NAME__-{}", env!("CARGO_PKG_VERSION")).is_ok();
    process::exit(if ok { 0 } else { 1 });
}

fn main() {
    // The only options are -v and --, so only the first argument can be one.
    let mut files: Vec<String> = env::args().skip(1).collect();
    match files.first().map(String::as_str) {
        Some("--") => {
            files.remove(0);
        }
        Some("-v") => version(),
        Some(arg) if arg.starts_with('-') && arg != "-" => usage(),
        _ => {}
    }
    if files.is_empty() {
        files.push("-".to_string());
    }
    let mut out = BufWriter::new(io::stdout().lock());
    for name in &files {
        cat(name, &mut out);
    }
    if let Err(e) = out.flush() {
        die(&format!("write error: {e}"));
    }
}

#[cfg(test)]
mod tests {
    use super::copy;
    use std::io::Cursor;

    #[test]
    fn copy_is_exact() {
        let data = b"a\nb\n".repeat(5000);
        let mut out = Vec::new();
        copy(&mut Cursor::new(&data), &mut out).unwrap();
        assert_eq!(out, data);
    }
}
