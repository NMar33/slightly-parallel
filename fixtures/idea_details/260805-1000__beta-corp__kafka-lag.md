---
id: id_bc_kafka
title: Add Kafka consumer lag alerts to Prometheus
---

## L2

Consumer lag > 10k messages for > 5min → PagerDuty page. Covers silent backpressure that currently only shows up when analytics counts diverge.
