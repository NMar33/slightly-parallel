---
id: nt_al_curl
title: Curl commands for testing auth flow locally
---

## L2

**Login** (get access + refresh):
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass"}'
```

**Refresh**:
```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Authorization: Bearer $REFRESH_TOKEN"
```

**Logout** (revokes refresh):
```bash
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```
