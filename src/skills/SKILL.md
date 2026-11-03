---
name: ub-mode
description: >
  Follow the reduced principles when writing or changing code. Every change
  follows First Make it Work, then Then Make it Right, then Follow Practice.
---

# ub-mode

Every time you are asked to make or review a change follow:
* First Make it Work.
* Then Make it Right.
* Follow Practice

# First Make it Work
## Laziness Protocol
* One decision lives in one place.
* Ship the smallest edit that solves the problem.

## Foundational Thinking
* Get the data shape right before you write the logic.
* Do first whatever helps every later phase.
* If a concurrent writer would matter, do not share state.

## Subtract Before You Add
* Take complexity out before you add anything.

## Architecture
### Model the Domain
* Put the domain in a structure that makes the illegal states impossible.
* If the code is already clear and local, leave it.

### Boundary Discipline
* Check the data where it enters. Inside, trust it.
* Keep the business logic in a pure function.

### Type System Discipline
* Make the illegal value impossible to write.
* Parse outside data once, where it comes in.

### Make Operations Idempotent
* Running it twice, or running it after a crash halfway through, ends in the same state.

# Then Make it Right
## Fix Root Causes
* Reproduce it. Fix the cause. A guard that only hides the crash is not a fix.

## Sequence work into verifiable units
* Finish one small unit and check it. Then start the next.

# Code Generation Quality Rules
* Never output placeholders, ellipses (...), or comments like '# rest of code'. Write complete, production-ready code.
* Preserve the exact indentation style (spaces/tabs) of the target file.
* Always include necessary imports and type annotations.
* Practice defensive coding: handle None, network/IO failures, and boundary edge cases.
* Keep changes minimal, robust, and verifiable.
