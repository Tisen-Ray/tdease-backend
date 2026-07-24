---
name: grill-with-docs
description: Grilling session that challenges your plan against the existing domain model, sharpens terminology, and updates documentation inline as decisions crystallise. Use when user wants to stress-test a plan against their project's language and documented decisions.
---

<what-to-do>

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time, waiting for feedback on each question before continuing.

If a question can be answered by exploring the codebase, explore the codebase instead.

</what-to-do>

<supporting-info>

## Domain awareness

During codebase exploration, read the project's domain docs first.

This project uses a `docs/` structure (not `CONTEXT.md + docs/adr/`). Start with `docs/agents/domain.md` for the full doc index. Key locations:

- `docs/ARCHITECTURE.md` — canonical terminology
- `docs/specs/` — design decisions
- `docs/record/` — past discoveries
- `docs/reference/` — technical reference

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in the project's domain docs, call it out immediately. "The architecture doc defines 'cancellation' as X, but you seem to mean Y — which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account' — do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"

### Update domain docs inline

When a term is resolved, update the relevant `docs/` file right there. Don't batch these up — capture them as they happen.

- **Glossary terms / terminology** → `docs/ARCHITECTURE.md` (or the appropriate architecture doc). See [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md) for the glossary style guide.
- **Design decisions** → a new file in `docs/specs/`
- **Discoveries** → `docs/record/`

Domain docs should be concise and free of implementation details. Don't treat them as scratch pads.

### Offer design docs sparingly

Only offer to create a spec in `docs/specs/` when all three are true:

1. **Hard to reverse** — the cost of changing your mind later is meaningful
2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons

If any of the three is missing, skip it. See [ADR-FORMAT.md](./ADR-FORMAT.md) for the spec template and guidance.

</supporting-info>
