# WCAG 2.2 quick reference (AA)

## New in 2.2

- **2.4.11 Focus Not Obscured / focus appearance**: focus indicator ≥3:1 against its
  background, ≥2 px outline, ~2 px offset; never hidden behind sticky headers.
- **2.5.7 Dragging Movements (AA)**: every drag action has a single-pointer alternative
  (buttons, clicks).
- **2.5.8 Target Size (Minimum) (AA)**: ≥24×24 CSS px; this project requires 44×44 px
  with ≥8 px between adjacent targets.
- **3.2.6 Consistent Help (A)**: help, search and contact links in the same place on
  every page.
- **3.3.7 Redundant Entry (A)**: don't make users re-enter data; auto-fill it
  (`autocomplete` attributes).

## Still applies from 2.1

- **1.4.3 Contrast (Minimum) (AA)**: normal text ≥4.5:1; large text (≥18 px, or ≥14 px
  bold) ≥3:1. Check: https://webaim.org/resources/contrastchecker/
- **1.4.11 Non-text Contrast (AA)**: UI component boundaries and icons ≥3:1.
- **2.1.1 Keyboard (A)**: all functionality by keyboard, no traps, logical tab order.
- **2.4.7 Focus Visible (AA)**: always visible focus indicator.
- **4.1.2 Name, Role, Value (A)**: every control has an accessible name and correct role;
  states (disabled, selected, busy, invalid) are exposed.

## Patterns

Icon-only button:
```html
<button aria-label="Close dialog"><svg aria-hidden="true">…</svg></button>
```

Form input with error:
```html
<label for="email">Email</label>
<input id="email" type="email" autocomplete="email" aria-required="true"
       aria-invalid="true" aria-describedby="email-error">
<span id="email-error" role="alert">Enter an email like name@example.com</span>
```

Loading button:
```html
<button aria-busy="true" disabled><span role="status">Saving…</span></button>
```

Also: semantic headings form an outline (`h1` > `h2` > `h3`); skip-to-content link on
pages with navigation; respect `prefers-reduced-motion`.
