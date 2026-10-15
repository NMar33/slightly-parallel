---
name: keep-the-architecture-page
description: "Write the next version of a project's Slightly Parallel architecture page: what the project is, what it does now, what it is made of and what is owed, as claims with their evidence. Use as a step of #architecture when the page is out of date, when the operator types #page, and as the last step of a #scan."
---

One page per project, kept in versions. You never write it from nothing:
you keep what is verified, correct what is wrong, and add what you touched.

1. Call `architecture_material`. The answer holds the computed facts, the
   current page, the claims to check again, and the instructions with the
   layout. With no current page, this version is the first: explore the
   folder as the instructions say.
2. Write the next version and send the whole page with
   `architecture_page {text, note}`. `note` is one line on what changed.
3. Read the `warnings` in the answer. A path the server did not find is
   corrected. Items that do not say how you know get their `seen:`. Write
   again until the warnings are ones you cannot fix, and tell the operator
   which those are.
4. Tell the operator in one sentence what this version changed.

{{part:architecture-page}}

Check: open the project's Architecture tab in Slightly Parallel. The page shows the
new version number, and no claim is marked "not found".

Mistakes to avoid: rewriting the page from nothing; describing a file you
did not open; a state word with no evidence; repeating the computed facts;
trusting an old README over the code; filling a section to make it look
complete.
