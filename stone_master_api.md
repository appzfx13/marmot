# Stone Master API — FE Integration Guide

**Base URL:** `/api/admin/stone-master/`  
**Auth:** Bearer Token (Admin / Super Admin only)  
**Content-Type:** `application/json`

---

## Endpoints Overview

| Method | URL | Action |
|--------|-----|--------|
| `GET` | `/api/admin/stone-master/` | List all stones |
| `POST` | `/api/admin/stone-master/` | Create a stone |
| `GET` | `/api/admin/stone-master/{id}/` | Get stone detail |
| `PATCH` | `/api/admin/stone-master/{id}/` | Update a stone |
| `DELETE` | `/api/admin/stone-master/{id}/` | Delete (soft) a stone |

---

## Fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | ✅ Yes | Unique. Max 100 chars. UI display label |
| `code` | string / null | ❌ No | Unique. Max 50 chars. For business logic use |
| `is_active` | boolean | ❌ No | Default: `true` |

---

## 1. List Stones

**`GET /api/admin/stone-master/`**

### Query Params (optional)
```
?search=ruby          → search by name or code
?is_active=true       → filter by active status
?name=Ruby            → filter by exact name
?code=RBY             → filter by exact code
?page=1               → pagination
```

### Response `200 OK`
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Ruby",
      "code": "RBY",
      "is_active": true,
      "created_at": "2026-09-07T10:00:00Z"
    },
    {
      "id": 2,
      "name": "Round Diamond",
      "code": "RD",
      "is_active": true,
      "created_at": "2026-09-07T10:05:00Z"
    }
  ]
}
```

---

## 2. Create Stone

**`POST /api/admin/stone-master/`**

### Request Body
```json
{
  "name": "Ruby",
  "code": "RBY",
  "is_active": true
}
```

### Minimal Request (only required field)
```json
{
  "name": "Emerald"
}
```

### Response `201 Created`
```json
{
  "name": "Ruby",
  "code": "RBY",
  "is_active": true
}
```

### Error — Duplicate name `400 Bad Request`
```json
{
  "name": ["master stone with this name already exists."]
}
```

### Error — Duplicate code `400 Bad Request`
```json
{
  "code": ["master stone with this code already exists."]
}
```

---

## 3. Get Stone Detail

**`GET /api/admin/stone-master/{id}/`**

### Response `200 OK`
```json
{
  "id": 1,
  "name": "Ruby",
  "code": "RBY",
  "is_active": true,
  "created_by_user": "Admin",
  "modified_by_user": "Admin"
}
```

---

## 4. Update Stone

**`PATCH /api/admin/stone-master/{id}/`**

> Send only the fields you want to update.

### Request Body
```json
{
  "name": "Ruby (Oval)",
  "is_active": false
}
```

### Response `200 OK`
```json
{
  "name": "Ruby (Oval)",
  "code": "RBY",
  "is_active": false
}
```

---

## 5. Delete Stone (Soft Delete)

**`DELETE /api/admin/stone-master/{id}/`**

### Response `204 No Content`
```
(empty body)
```

---

## Sample Stone Records (for seed data reference)

```json
[
  { "name": "Round Diamond",   "code": "RD"  },
  { "name": "Princess Diamond","code": "PD"  },
  { "name": "Oval Diamond",    "code": "OD"  },
  { "name": "Ruby",            "code": "RBY" },
  { "name": "Emerald",         "code": "EMR" },
  { "name": "Sapphire",        "code": "SPH" },
  { "name": "Pearl",           "code": "PRL" },
  { "name": "Coral",           "code": "CRL" },
  { "name": "Topaz",           "code": "TPZ" }
]
```

---

## Notes for FE

- `id` is returned in **List** and **Detail** responses only — not in Create/Update response.
- Use `PATCH` (not `PUT`) for updates — send only changed fields.
- Soft-deleted stones disappear from list but are not permanently removed from DB.
- `code` field is optional but recommended — it can be used as a stable identifier for business logic in future.
