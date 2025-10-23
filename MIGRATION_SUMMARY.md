# Migration Summary: Add alert_suppression_seconds

## Overview
This migration adds the `alert_suppression_seconds` column to the `monitoring_config` table.

## Files Created/Modified

### New Files:
1. **migrations/** - Flask-Migrate directory structure
   - `migrations/alembic.ini` - Alembic configuration
   - `migrations/env.py` - Migration environment setup
   - `migrations/script.py.mako` - Template for new migrations
   - `migrations/versions/c007c9af2919_add_alert_suppression_seconds_to_.py` - The migration file

2. **add_alert_suppression_column.py** - Helper script for users with existing databases
   - Safely adds the column if it doesn't exist
   - Provides clear instructions for next steps

3. **migrations/MIGRATION_GUIDE.md** - Detailed guide for database migrations
   - Common migration tasks
   - Troubleshooting tips
   - Manual migration instructions

### Modified Files:
1. **README.md** - Added section 4.4 "升级现有数据库 (Updating Existing Database)"
   - Instructions for upgrading existing installations
   - Reference to helper script and migration guide

## Migration Details

### Column Specification:
- **Name**: `alert_suppression_seconds`
- **Type**: INTEGER
- **Nullable**: NOT NULL
- **Default**: 600 (10 minutes)

### Migration Features:
- **Idempotent**: Checks if column exists before adding it
- **Safe**: Uses SQLite batch_alter_table for compatibility
- **Reversible**: Includes downgrade function

### Usage Instructions:

#### For New Installations:
```bash
flask init-db           # Initialize database with sample data
flask db upgrade        # Apply migrations
python run.py           # Start the app
```

#### For Existing Installations:
```bash
# Option 1: Using helper script (recommended)
python add_alert_suppression_column.py
flask db upgrade

# Option 2: Direct upgrade (if no column conflict)
flask db upgrade

# Option 3: Manual (if flask db upgrade fails)
# See README.md section 4.4 or migrations/MIGRATION_GUIDE.md
```

## Testing Performed

1. ✓ Fresh database creation with `flask init-db`
2. ✓ Migration application on fresh database
3. ✓ Old schema database upgrade using helper script
4. ✓ Old schema database upgrade using flask db upgrade
5. ✓ Application startup with migrated database
6. ✓ Idempotent migration (running twice doesn't error)
7. ✓ Helper script on already-migrated database

## Notes

The migration is designed to handle the chicken-and-egg problem where:
- The app tries to query the database during initialization
- The database doesn't have the new column yet
- Flask-Migrate needs the app to initialize to run migrations

The solution provides multiple paths for users to successfully upgrade their databases.




# 直接添加索引，不管迁移系统
sqlite3 instance/monitoring_data.db << 'EOF'
-- 添加性能索引
CREATE INDEX IF NOT EXISTS idx_log_site_timestamp ON health_check_log(site_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_log_timestamp ON health_check_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_site_active ON monitored_site(is_active);
-- 验证索引
SELECT 'Indexes created:' as status;
SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='health_check_log';
EOF