---
id: id_al_openapi
title: Generate SDK from OpenAPI spec automatically via CI
---

## L2

Post-merge to main → CI runs openapi-generator → publishes TS + Python packages to private registry with git-sha version. Consumers pin to sha. Eliminates SDK drift.
