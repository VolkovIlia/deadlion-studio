# Question bank

Templates for AskUserQuestion. One block = one call (≤4 questions). Adapt labels to
the idea, translate to the user's language, drop questions already answered by the
project docs, and keep `multiSelect` as shown.

## Business

1. **Goal** (header `Goal`, single): What is the main business goal?
   - Acquisition — more sign-ups
   - Retention — less churn, higher DAU/MAU
   - Monetization — higher ARPU or paid conversion
   - Automation — less manual work, faster processes
2. **Constraints** (header `Constraints`, multi): What constraints apply?
   - Time (< 2 weeks) — hard deadline
   - Budget — limited development resources
   - Compliance (GDPR/PCI) — regulatory requirements
   - No hard constraints — flexible timeline

## Users

1. **Primary user** (header `User`, single): Who is the primary user?
   - B2C end users — mass market, individuals
   - B2B companies/teams — business customers, SaaS
   - Developers/technical users — APIs, tools
   - Internal users — company employees
2. **Alternatives** (header `Alternatives`, multi): What do users use today?
   - Spreadsheets — manual Excel/Google Sheets
   - Competing product — name it
   - Custom in-house solution
   - Nothing — the pain is unsolved

## Value

1. **North Star** (header `North Star`, single): Which metric defines success?
   - DAU/MAU — daily/monthly active users
   - Conversion to the key action — % of users who complete it
   - Retention D7/D30 — users returning after 7/30 days
   - Revenue/ARPU — revenue or average revenue per user

## Delivery

1. **Core** (header `Core`, multi): What must the first release contain?
   - Sign-up / login
   - CRUD of the main entity
   - Integration with an external API (payments, messaging, …)
   - Admin panel
2. **First risk** (header `Risk`, single): Which risk must be tested first?
   - Technical feasibility — can we build it?
   - Demand — do users need it?
   - Unit economics — will it be profitable?
   - Regulatory — is it legal?

## Clarity-scan question shape

For an ambiguity found in the scan, prefix the question with its category and
offer quantified options, e.g. `[Non-functional] "Fast API response" — which SLA?`:
P95 < 100 ms (cache + DB tuning) · P95 < 500 ms (standard) · P95 < 2 s (MVP minimum) ·
decide after launch from real metrics.
