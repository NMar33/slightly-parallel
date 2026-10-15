---
key: skill
section: 4
title: Skill
enabled: true
command: #skill | Write the skill from what was done in this chat (Skill, section 4)
---

**Skill — `#skill`.** The operator wants what was just done to become a
skill: a procedure any agent loads when a task matches. The server keeps
the message and the hook names the id. Write the draft from what actually
happened in this chat, not from general knowledge:
`skill_draft {id, skill_md, files, note}` — `skill_md` is the whole
SKILL.md; `files` is `{"scripts/check.sh": "…"}`, relative paths to text.

SKILL.md starts with a `---` block: `name` — lowercase letters, digits and
single hyphens, the folder name agents see; `description` — what the skill
does and when to use it, in the words the operator uses when asking for
it, at most 1,024 characters. Agents read only the description when they
choose a skill. The body: the steps in order, the exact commands, the check
that proves it worked, and the mistakes made in this chat that the next
agent should avoid. Put long reference text and scripts in `files` and
link them from SKILL.md. When you rewrite SKILL.md later, leave `files`
out to keep the ones the skill has; send `{}` only to remove them. The
answer lists `checks`: fix every error and write again. The operator reads
the draft on the Skills page and decides where it is installed; you do not
install skills.
