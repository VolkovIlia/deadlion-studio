// See LICENSE file for copyright and license details.
//
// Key decoding, filtering and drawing. Pure functions; no IO.

use std::fmt::Write;

use crate::config;

const ESC: char = '\x1b';
/// Second char of a CSI sequence (`ESC [`) and of an SS3 sequence (`ESC O`).
const CSI: char = '\x5b';
const SS3: char = 'O';
const CLEAR: &str = "\x1b[0m\x1b[2J";

#[derive(Debug, PartialEq)]
pub enum Key {
    Char(char),
    Backspace,
    Up,
    Down,
    Enter,
    Cancel,
}

#[derive(Debug, PartialEq)]
pub enum Step {
    Continue,
    Pick(String),
    Cancel,
}

/// Turn raw terminal input into keys.
pub fn decode(buf: &[u8]) -> Vec<Key> {
    let chars: Vec<char> = String::from_utf8_lossy(buf).chars().collect();
    let mut keys = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let (key, used) = decode_one(&chars[i..]);
        keys.extend(key);
        i += used;
    }
    keys
}

/// Decode the key at the start of C; return it and the chars it used.
fn decode_one(c: &[char]) -> (Option<Key>, usize) {
    match c[0] {
        '\r' | '\n' => (Some(Key::Enter), 1),
        '\x7f' | '\x08' => (Some(Key::Backspace), 1),
        '\x03' => (Some(Key::Cancel), 1),
        '\x0e' => (Some(Key::Down), 1),
        '\x10' => (Some(Key::Up), 1),
        ESC => decode_escape(c),
        ch if ch < ' ' => (None, 1),
        ch => (Some(Key::Char(ch)), 1),
    }
}

/// Decode an escape sequence; a lone trailing ESC is the Esc key.
fn decode_escape(c: &[char]) -> (Option<Key>, usize) {
    match (c.get(1).copied(), c.get(2).copied()) {
        (None, _) => (Some(Key::Cancel), 1),
        (Some(CSI | SS3), Some('A')) => (Some(Key::Up), 3),
        (Some(CSI | SS3), Some('B')) => (Some(Key::Down), 3),
        (Some(SS3), Some(_)) => (None, 3),
        (Some(CSI), _) => (None, csi_len(c)),
        _ => (None, 1),
    }
}

/// Length of the CSI sequence at the start of C, through its final byte.
fn csi_len(c: &[char]) -> usize {
    let is_final = |ch: &char| ('\x40'..='\x7e').contains(ch);
    c[2..].iter().position(is_final).map_or(c.len(), |p| p + 3)
}

/// First COLS chars of S with tabs as spaces and control chars dropped.
fn fit(s: &str, cols: usize) -> String {
    let shown = s.chars().filter_map(|c| match c {
        '\t' => Some(' '),
        c if c.is_control() => None,
        c => Some(c),
    });
    shown.take(cols).collect()
}

/// Parse "#rrggbb" into its three channels.
fn rgb(hex: &str) -> Option<[u8; 3]> {
    let digits = hex.strip_prefix('#').filter(|d| d.len() == 6)?;
    let channel = |i: usize| u8::from_str_radix(digits.get(i..i + 2)?, 16).ok();
    Some([channel(0)?, channel(2)?, channel(4)?])
}

/// Truecolor SGR for FG on BG; empty when either is unparsable.
fn sgr(fg: &str, bg: &str) -> String {
    match (rgb(fg), rgb(bg)) {
        (Some([r, g, b]), Some([br, bgr, bb])) => {
            format!("\x1b[38;2;{r};{g};{b};48;2;{br};{bgr};{bb}m")
        }
        _ => String::new(),
    }
}

/// Attributes of (normal, selected) rows.
fn attrs(color: bool) -> (String, String) {
    if !color {
        return ("\x1b[0m".to_string(), "\x1b[7m".to_string());
    }
    (sgr(config::NORM_FG, config::NORM_BG), sgr(config::SEL_FG, config::SEL_BG))
}

/// Append screen row R (1-based): clear it in ATTR, then TEXT.
fn put_row(out: &mut String, r: usize, attr: &str, text: &str) {
    let _ = write!(out, "\x1b[{r};1H{attr}\x1b[K{text}");
}

pub struct State {
    items: Vec<String>,
    /// Lowercased items, built once so filtering does not allocate per key.
    lower: Vec<String>,
    query: String,
    matches: Vec<usize>,
    sel: usize,
    top: usize,
}

impl State {
    pub fn new(items: Vec<String>) -> State {
        let lower = items.iter().map(|s| s.to_lowercase()).collect();
        let matches = (0..items.len()).collect();
        State { items, lower, query: String::new(), matches, sel: 0, top: 0 }
    }

    pub fn handle(&mut self, key: Key) -> Step {
        match key {
            Key::Char(c) => {
                self.query.push(c);
                self.refilter();
            }
            Key::Backspace => {
                self.query.pop();
                self.refilter();
            }
            Key::Up => self.sel = self.sel.saturating_sub(1),
            Key::Down => self.sel = (self.sel + 1).min(self.matches.len().saturating_sub(1)),
            Key::Enter => return self.picked(),
            Key::Cancel => return Step::Cancel,
        }
        Step::Continue
    }

    fn picked(&self) -> Step {
        match self.matches.get(self.sel) {
            Some(&i) => Step::Pick(self.items[i].clone()),
            None => Step::Continue,
        }
    }

    /// Case-insensitive substring match of every item against the query.
    fn refilter(&mut self) {
        let q = self.query.to_lowercase();
        self.matches = (0..self.items.len()).filter(|&i| self.lower[i].contains(&q)).collect();
        self.sel = 0;
        self.top = 0;
    }

    /// Scroll so the selection is visible in a list of LIST rows.
    fn scroll(&mut self, list: usize) {
        self.top = self.top.min(self.matches.len().saturating_sub(list));
        if self.sel < self.top {
            self.top = self.sel;
        }
        if self.sel >= self.top + list {
            self.top = self.sel + 1 - list;
        }
    }

    /// The whole screen for a ROWS x COLS terminal as one escape string.
    pub fn draw(&mut self, rows: usize, cols: usize, color: bool) -> String {
        if rows < 3 || cols < 10 {
            return CLEAR.to_string();
        }
        let (norm, sel) = attrs(color);
        let list = rows - 2;
        self.scroll(list);
        let prompt = format!("{}{}", config::PROMPT, self.query);
        let mut out = String::new();
        put_row(&mut out, 1, &norm, &fit(&prompt, cols));
        for r in 0..list {
            let selected = !self.matches.is_empty() && self.top + r == self.sel;
            let attr = if selected { &sel } else { &norm };
            put_row(&mut out, r + 2, attr, &self.list_row(r, cols));
        }
        put_row(&mut out, rows, &norm, &fit(&self.status(), cols));
        let col = (prompt.chars().count() + 1).min(cols);
        let _ = write!(out, "\x1b[0m\x1b[1;{col}H");
        out
    }

    /// Text of list row R; the selected line is padded to COLS.
    fn list_row(&self, r: usize, cols: usize) -> String {
        if self.matches.is_empty() {
            return fit(if r == 0 { "  (no match)" } else { "" }, cols);
        }
        let Some(&i) = self.matches.get(self.top + r) else {
            return String::new();
        };
        if self.top + r != self.sel {
            return fit(&format!("  {}", self.items[i]), cols);
        }
        let line = fit(&format!("> {}", self.items[i]), cols);
        let pad = cols - line.chars().count();
        line + &" ".repeat(pad)
    }

    fn status(&self) -> String {
        let pos = if self.matches.is_empty() { 0 } else { self.sel + 1 };
        format!("{pos}/{}  Up/Down move  Enter pick  Esc cancel", self.matches.len())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn typed(query: &str) -> State {
        let items = ["alpha", "beta", "gamma"].map(String::from).to_vec();
        let mut state = State::new(items);
        for c in query.chars() {
            state.handle(Key::Char(c));
        }
        state
    }

    #[test]
    fn decode_table() {
        let cases: &[(&[u8], &[Key])] = &[
            (b"\r", &[Key::Enter]),
            (b"\n", &[Key::Enter]),
            (b"\x7f", &[Key::Backspace]),
            (b"\x08", &[Key::Backspace]),
            (b"\x03", &[Key::Cancel]),
            (b"\x0e", &[Key::Down]),
            (b"\x1b[B", &[Key::Down]),
            (b"\x1bOB", &[Key::Down]),
            (b"\x10", &[Key::Up]),
            (b"\x1b[A", &[Key::Up]),
            (b"\x1bOA", &[Key::Up]),
            (b"\x1b", &[Key::Cancel]),
            (b"\x1b[1;5Cx", &[Key::Char('x')]),
            (b"\x01", &[]),
            (b"a\xc3\xa9", &[Key::Char('a'), Key::Char('\u{e9}')]),
        ];
        for (input, want) in cases {
            assert_eq!(decode(input), *want, "{input:?}");
        }
    }

    #[test]
    fn filter_is_case_insensitive() {
        let mut state = typed("GA");
        assert_eq!(state.handle(Key::Enter), Step::Pick("gamma".to_string()));
    }

    #[test]
    fn selection_is_clamped() {
        let mut state = typed("");
        for _ in 0..5 {
            state.handle(Key::Down);
        }
        assert_eq!(state.handle(Key::Enter), Step::Pick("gamma".to_string()));
        state.handle(Key::Up);
        state.handle(Key::Up);
        state.handle(Key::Up);
        assert_eq!(state.handle(Key::Enter), Step::Pick("alpha".to_string()));
    }

    #[test]
    fn draw_shows_prompt_and_selection() {
        let screen = typed("ga").draw(12, 40, true);
        assert!(screen.contains("filter: ga"));
        assert!(screen.contains("> gamma"));
        assert!(screen.contains("38;2"));
    }

    #[test]
    fn no_color_has_no_truecolor() {
        let screen = typed("ga").draw(12, 40, false);
        assert!(!screen.contains("38;2") && !screen.contains("48;2"));
        assert!(screen.contains("\x1b[7m"));
    }

    #[test]
    fn tiny_terminal_is_only_cleared() {
        assert_eq!(typed("").draw(2, 5, true), CLEAR);
    }

    #[test]
    fn enter_without_match_continues() {
        let mut state = typed("zzz");
        assert_eq!(state.handle(Key::Enter), Step::Continue);
        assert!(state.draw(12, 40, true).contains("(no match)"));
    }
}
