# Database Migrations

Schema versioning and migration management.

## Structure

```
migrations/
├── run.py           # Migration runner (apply, rollback, status, list)
├── versions/        # Migration SQL files
│   ├── 001_initial_schema.sql
│   ├── 002_add_feature.sql
│   └── ...
└── README.md        # This file
```

## Creating a Migration

1. Create a file in `versions/` with format: `NNN_description.sql`
2. Use this structure:

```sql
-- Up
CREATE TABLE my_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255)
);

-- Down
DROP TABLE my_table;
```

The `-- Up` section runs when applying. The `-- Down` section runs when rolling back.

## Running Migrations

### Apply all pending migrations:
```bash
python migrations/run.py apply
```

### Check migration status:
```bash
python migrations/run.py status
```

### List available migrations:
```bash
python migrations/run.py list
```

### Rollback a specific migration:
```bash
python migrations/run.py rollback 001_initial_schema
```

## Tracking

Migrations are tracked in the `schema_version` table:
- `version`: Migration filename (without .sql)
- `applied_at`: When it was applied
- `rolled_back_at`: When (if) it was rolled back (NULL if still applied)

## Best Practices

- Migrations are **irreversible in production** — test rollbacks in dev/staging first
- Keep migrations **atomic** — one logical change per file
- **Always include DOWN SQL** — even if it's just for documentation
- Name migrations clearly: `NNN_what_it_does.sql`
- Test both up and down: `apply` then `rollback` in dev
- Number migrations sequentially: `001`, `002`, `003`, etc.
