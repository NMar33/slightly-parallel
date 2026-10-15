---
id: id_al_dogfood
title: Dogfood the rate limiter internally before shipping publicly
---

## L2

Route internal-tools traffic through the same rate limiter middleware for a week before enabling on public endpoints. Catches config bugs against real usage patterns without customer blast radius. Cost: 1-2 days to add feature flag + gradual rollout.
