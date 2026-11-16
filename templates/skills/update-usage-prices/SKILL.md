---
name: update-usage-prices
description: "Update the API prices Slightly Parallel's Usage page counts dollars with: a helper agent reads the providers' own pricing pages and writes them. Use only when the operator types #usage-price."
---

The operator typed `#usage-price`. The Usage page counts its dollars with
these prices. Only the operator starts this.

1. **Say what you are about to do**, in one line, with the pages: "Understood,
   updating the prices. Going to platform.claude.com and developers.openai.com."
2. **Start one helper agent** (in Claude Code: the Agent tool with `model`
   opus; in another tool, on the chat's model). Give it this whole prompt and
   nothing else:

   > Update the API prices of Slightly Parallel. Call the MCP tool
   > `usage_prices_material`. Follow the `instructions` in the answer exactly.
   > Then call `usage_prices_write {models, sources, note}`. Reply with what its
   > answer says changed, its warnings, and the models you left out.

   If your tool has no helper agents, do the same steps yourself.
3. **Tell the operator** what changed, model by model with the old and the new
   price, any warning, and the models left without a price. Nothing changed:
   say so in one line.

The days before an update keep their old prices, so an update never rewrites
the past. A refusal from `usage_prices_write` names what is wrong: fix it and
write again.

Mistakes to avoid: updating without the command; a price from memory or from
another site; filling in a price the page does not show.
