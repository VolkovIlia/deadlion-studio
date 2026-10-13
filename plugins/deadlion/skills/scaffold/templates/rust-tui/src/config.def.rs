// See LICENSE file for copyright and license details.
// Copied to config.rs on the first build; edit config.rs, not this file.
// Colours are "#rrggbb"; a non-empty NO_COLOR disables them.
pub const NORM_FG: &str = "#bbbbbb";
pub const NORM_BG: &str = "#222222";
pub const SEL_FG: &str = "#eeeeee";
pub const SEL_BG: &str = "#005577";
// dl-contrast: NORM_FG NORM_BG 4.5
// dl-contrast: SEL_FG SEL_BG 4.5
/// Text in front of the filter on the top line.
pub const PROMPT: &str = "filter: ";
