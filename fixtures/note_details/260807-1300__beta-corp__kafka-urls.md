---
id: nt_bc_kafka_url
title: Kafka broker URLs staging vs prod
---

## L2

- **staging**: `kafka-staging-1.internal:9092,kafka-staging-2.internal:9092`
- **prod**: `kafka-prod-1.internal:9092,kafka-prod-2.internal:9092,kafka-prod-3.internal:9092`

Both clusters use SASL_SSL. Credentials in Vault at `secret/kafka/{env}/consumer`.
