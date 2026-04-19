import sqlite3
import os

# Database path
db_path = 'workspace/memory/axelo.db'

if os.path.exists(db_path):
    print(f'Found database at: {db_path}')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check existing columns
    cursor.execute('PRAGMA table_info(sitepattern)')
    columns = [row[1] for row in cursor.fetchall()]
    print(f'Current columns: {columns}')
    
    # Add missing columns
    if 'signature_headers' not in columns:
        cursor.execute("ALTER TABLE sitepattern ADD COLUMN signature_headers TEXT DEFAULT ''")
        print('Added signature_headers')
    
    if 'antibot_error_codes' not in columns:
        cursor.execute("ALTER TABLE sitepattern ADD COLUMN antibot_error_codes TEXT DEFAULT ''")
        print('Added antibot_error_codes')
    
    if 'requires_bridge' not in columns:
        cursor.execute('ALTER TABLE sitepattern ADD COLUMN requires_bridge INTEGER DEFAULT 0')
        print('Added requires_bridge')
    
    if 'session_refresh_needed' not in columns:
        cursor.execute('ALTER TABLE sitepattern ADD COLUMN session_refresh_needed INTEGER DEFAULT 0')
        print('Added session_refresh_needed')
    
    conn.commit()
    conn.close()
    print('Database schema updated!')
else:
    print(f'Database not found at: {db_path}')
