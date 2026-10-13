# UX anti-patterns

Check every design plan against these before implementation. A hit means change the plan.

## Generic "AI-looking" / SaaS clichés

| Anti-pattern | Fix |
|---|---|
| Purple/blue gradients, floating particles, glow effects | Palette derived from the product's domain; flat surfaces |
| Gradient hero with centred headline + two buttons | Lead with the product's actual content or primary task |
| Card grid by default for every list | Choose the layout from the data: table, list, timeline, single column |
| All-caps eyebrow label above every heading | Plain heading hierarchy; one label style at most |
| Three feature cards with icons | Show the feature working (screenshot, live example) |
| Emoji as icons, rounded-everything, drop shadow on everything | One radius, one elevation level, real icon set |
| Several competing accents | One accent colour, used only for the primary action and focus |

## Visual

| Anti-pattern | Problem | Fix |
|---|---|---|
| Carousel as primary content | ~1% click-through, hides content | Static hero or visible tabs |
| Hamburger menu on desktop | Hides primary navigation | Visible top nav; hamburger only below 768 px |
| Infinite scroll without pagination | No position, breaks back button, inaccessible | Pagination or "Load more" with total count |
| Placeholder text as label | Disappears on focus, fails contrast | Persistent label above the field |

## Dark patterns (always reject)

| Pattern | Description |
|---|---|
| Confirmshaming | "No thanks, I don't want to save money" |
| Roach motel | Easy signup, hard cancellation (illegal under EU consumer law) |
| Forced continuity | Trial auto-charges without clear warning |
| Hidden costs | Fees revealed only at checkout |
| Misdirection | Visual hierarchy steers users into the wrong action |
| Trick questions | Double negatives in opt-out checkboxes; GDPR needs clear consent |

## Interaction

| Anti-pattern | Problem | Fix |
|---|---|---|
| Modal on page load | Blocks content; most users close it | Inline banner or delayed non-blocking prompt |
| Disabled submit without explanation | User can't tell what's wrong | Keep enabled; show inline errors on submit |
| Custom scrollbar replacing native | Breaks trackpad/touch and accessibility | Native scrollbar styled with `scrollbar-*` CSS |
| Hover-only tooltip for essential info | Hover doesn't exist on touch | Inline text or tap-to-reveal |
| Auto-advancing forms | Removes control, causes errors | Explicit "Next" with progress indicator |

## Terminal

| Anti-pattern | Problem | Fix |
|---|---|---|
| Spinner or animation redrawn while idle | Burns CPU, flickers, floods slow links and tmux | Redraw only on input, resize or new data |
| Full clear on every keystroke | Flicker, slow over ssh | One write per frame of the changed rows |
| Mouse-only actions | Unusable over ssh, in pipes and for keyboard users | A key for every action |
| Colour as the only state signal | Lost on monochrome, NO_COLOR and for colour-blind users | Marker or reverse video |
| Truecolor palette without a NO_COLOR path | Ignores the user's opt-out | Honour NO_COLOR |
| UI drawn on stdout | Corrupts the pipe the program sits in | Draw on /dev/tty |
| Boxes around every panel | Wastes cells and adds noise | One separator line |
| Bindings on Ctrl-s/Ctrl-z/Ctrl-q | Collide with flow control and job control | Standard keys only |
