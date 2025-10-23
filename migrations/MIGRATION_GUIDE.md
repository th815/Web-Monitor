# Database Migration Guide

This project uses Flask-Migrate (Alembic) for database schema migrations.

## Common Migration Tasks

### Applying Pending Migrations

If you encounter an error like "no such column: monitoring_config.alert_suppression_seconds", you need to apply pending migrations.

**Option 1: Using Flask-Migrate CLI (Recommended for new databases)**

If you have a new/empty database:
```bash
source .venv/bin/activate  # Activate your virtual environment
python -m flask db upgrade
```

**Option 2: Manual Migration (For existing databases with data)**

If the app won't start because of missing columns, apply the migration manually:

```bash
source .venv/bin/activate
cd /home/engine/project
python3 << 'EOF'
import sqlite3
from config import SQLALCHEMY_DATABASE_URI
import re

# Extract database path from URI
match = re.search(r'sqlite:///(.+)', SQLALCHEMY_DATABASE_URI)
if match:
    db_path = match.group(1)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(monitoring_config)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'alert_suppression_seconds' not in columns:
        print("Adding alert_suppression_seconds column...")
        cursor.execute('''
            ALTER TABLE monitoring_config 
            ADD COLUMN alert_suppression_seconds INTEGER NOT NULL DEFAULT 600
        ''')
        conn.commit()
        print("✓ Column added successfully!")
    else:
        print("Column already exists!")
    
    conn.close()
EOF

# Now apply Flask migrations to update version tracking
python -m flask db upgrade
```

### Creating New Migrations

When you modify models in `app/models.py`:

```bash
source .venv/bin/activate
python -m flask db migrate -m "Description of changes"
```

Review the generated migration file in `migrations/versions/` before applying it.

### Checking Migration Status

```bash
python -m flask db current  # Show current migration version
python -m flask db history  # Show migration history
```

## Troubleshooting

### Error: "no such column" when running migrations

This happens because the app tries to query the database during initialization. Use Option 2 above to manually add the column first.

### Error: "FAILED: No 'script_location' key found"

Don't use `alembic` commands directly. Use `flask db` commands instead.
