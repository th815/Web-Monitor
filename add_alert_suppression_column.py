#!/usr/bin/env python3
"""
Helper script to add the alert_suppression_seconds column to existing databases.

This script is useful when you have an existing database and encounter the error:
"no such column: monitoring_config.alert_suppression_seconds"

Usage:
    python add_alert_suppression_column.py

After running this script, apply the Flask migration:
    python -m flask db upgrade
"""
import sqlite3
import os
import sys

def add_column_if_missing():
    """Add alert_suppression_seconds column if it doesn't exist."""
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, 'instance', 'monitoring_data.db')
    
    if not os.path.exists(db_path):
        print(f"✗ Database not found at: {db_path}")
        print("  Please run the app once to create the database, or use: flask init-db")
        return 1
    
    print(f"Checking database at: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if monitoring_config table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monitoring_config'")
        if not cursor.fetchone():
            print("✗ monitoring_config table not found in database")
            conn.close()
            return 1
        
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
            
            # Verify
            cursor.execute("PRAGMA table_info(monitoring_config)")
            updated_columns = [col[1] for col in cursor.fetchall()]
            if 'alert_suppression_seconds' in updated_columns:
                print("✓ Verification passed")
            else:
                print("✗ Verification failed")
                conn.close()
                return 1
        else:
            print("✓ Column already exists!")
        
        conn.close()
        print("\nNext steps:")
        print("  1. Run: python -m flask db upgrade")
        print("  2. Start your app: python run.py")
        return 0
        
    except sqlite3.Error as e:
        print(f"✗ Database error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"✗ Unexpected error: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(add_column_if_missing())
