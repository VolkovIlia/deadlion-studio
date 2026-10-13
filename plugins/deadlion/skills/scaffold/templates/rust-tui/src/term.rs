// See LICENSE file for copyright and license details.
//
// The controlling terminal in raw mode on the alternate screen.
// All unsafe code of __NAME__ lives in this file.

use std::fs::{File, OpenOptions};
use std::io::{self, ErrorKind, Read, Write};
use std::mem;
use std::os::unix::io::{AsRawFd, RawFd};
use std::panic;
use std::ptr;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;

/// Set by SIGTERM, SIGHUP and SIGINT; the main loop then cancels so that
/// Drop restores the terminal.
static QUIT: AtomicBool = AtomicBool::new(false);

/// The tty fd and its original mode, for the panic hook: with
/// `panic = "abort"` Drop never runs on a panic. One Tty per process.
static SAVED: OnceLock<(RawFd, libc::termios)> = OnceLock::new();

/// True while the Tty is open; the panic hook must not touch a closed fd.
static ACTIVE: AtomicBool = AtomicBool::new(false);

pub struct Tty {
    file: File,
    orig: libc::termios,
}

extern "C" fn on_signal(sig: libc::c_int) {
    if sig != libc::SIGWINCH {
        QUIT.store(true, Ordering::SeqCst);
    }
}

/// Catch the quit signals, and SIGWINCH so a resize interrupts poll at once.
fn catch_signals() {
    let handler = on_signal as extern "C" fn(libc::c_int) as libc::sighandler_t;
    for sig in [libc::SIGTERM, libc::SIGHUP, libc::SIGINT, libc::SIGWINCH] {
        // SAFETY: sigaction is plain data; the handler only stores an atomic.
        unsafe {
            let mut sa: libc::sigaction = mem::zeroed();
            sa.sa_sigaction = handler;
            libc::sigemptyset(&mut sa.sa_mask);
            libc::sigaction(sig, &sa, ptr::null_mut());
        }
    }
}

/// True once a quit signal arrived.
pub fn interrupted() -> bool {
    QUIT.load(Ordering::SeqCst)
}

/// Leave the alternate screen and put back the original terminal mode.
fn restore(fd: RawFd, orig: &libc::termios) {
    let seq = b"\x1b[0m\x1b[?1049l";
    // SAFETY: fd is the open tty; seq and orig are valid for these calls.
    unsafe {
        libc::write(fd, seq.as_ptr().cast(), seq.len());
        libc::tcsetattr(fd, libc::TCSAFLUSH, orig);
    }
}

/// Restore the terminal before the default hook prints a panic message, so
/// the message lands on the normal screen in cooked mode.
fn restore_on_panic(fd: RawFd, orig: libc::termios) {
    if SAVED.set((fd, orig)).is_err() {
        return;
    }
    let previous = panic::take_hook();
    panic::set_hook(Box::new(move |info| {
        if let (true, Some((fd, orig))) = (ACTIVE.swap(false, Ordering::SeqCst), SAVED.get()) {
            restore(*fd, orig);
        }
        previous(info);
    }));
}

/// Open /dev/tty, switch it to raw mode and enter the alternate screen.
pub fn open() -> io::Result<Tty> {
    let file = OpenOptions::new().read(true).write(true).open("/dev/tty")?;
    let fd = file.as_raw_fd();
    // SAFETY: termios is plain data filled by tcgetattr on a valid fd.
    let mut orig: libc::termios = unsafe { mem::zeroed() };
    if unsafe { libc::tcgetattr(fd, &mut orig) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let mut raw = orig;
    // SAFETY: raw is a valid termios copied from orig.
    unsafe { libc::cfmakeraw(&mut raw) };
    if unsafe { libc::tcsetattr(fd, libc::TCSAFLUSH, &raw) } != 0 {
        return Err(io::Error::last_os_error());
    }
    catch_signals();
    restore_on_panic(fd, orig);
    ACTIVE.store(true, Ordering::SeqCst);
    let mut tty = Tty { file, orig };
    tty.write("\x1b[?1049h")?;
    Ok(tty)
}

impl Tty {
    /// Terminal size as (rows, cols); (24, 80) when unknown.
    pub fn size(&self) -> (usize, usize) {
        // SAFETY: winsize is plain data filled by TIOCGWINSZ on a valid fd.
        let mut ws: libc::winsize = unsafe { mem::zeroed() };
        let r = unsafe { libc::ioctl(self.file.as_raw_fd(), libc::TIOCGWINSZ, &mut ws) };
        if r != 0 || ws.ws_row == 0 || ws.ws_col == 0 {
            return (24, 80);
        }
        (usize::from(ws.ws_row), usize::from(ws.ws_col))
    }

    /// Wait up to TIMEOUT_MS for input; an empty result means none arrived.
    pub fn read(&mut self, timeout_ms: i32) -> io::Result<Vec<u8>> {
        let mut pfd = libc::pollfd { fd: self.file.as_raw_fd(), events: libc::POLLIN, revents: 0 };
        // SAFETY: pfd is one valid pollfd.
        match unsafe { libc::poll(&mut pfd, 1, timeout_ms) } {
            0 => return Ok(Vec::new()),
            n if n < 0 => {
                let err = io::Error::last_os_error();
                let eintr = err.kind() == ErrorKind::Interrupted;
                return if eintr { Ok(Vec::new()) } else { Err(err) };
            }
            _ => {}
        }
        let mut buf = [0u8; 1024];
        match self.file.read(&mut buf) {
            Ok(0) => Err(io::Error::new(ErrorKind::UnexpectedEof, "end of file")),
            Ok(n) => Ok(buf[..n].to_vec()),
            Err(e) if e.kind() == ErrorKind::Interrupted => Ok(Vec::new()),
            Err(e) => Err(e),
        }
    }

    pub fn write(&mut self, s: &str) -> io::Result<()> {
        self.file.write_all(s.as_bytes())?;
        self.file.flush()
    }
}

impl Drop for Tty {
    fn drop(&mut self) {
        if ACTIVE.swap(false, Ordering::SeqCst) {
            restore(self.file.as_raw_fd(), &self.orig);
        }
    }
}
