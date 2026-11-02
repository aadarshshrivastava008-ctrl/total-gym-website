import re
import os
import sqlite3
import datetime
from urllib.parse import quote_plus
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# PostgreSQL (Supabase) Driver Check
try:
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except ImportError:
    HAS_PG = False

app = Flask(__name__, static_folder='.')
CORS(app)

DB_FILE = 'tickets.db'

# 🟢 SUPABASE CLOUD DATABASE CONFIGURATION
DB_PASS = quote_plus("r-THx9s8!y879SX")
DEFAULT_SUPABASE_URL = f"postgresql://postgres:{DB_PASS}@db.vacizclcpntndpsvqpoi.supabase.co:5432/postgres"

def clean_db_url(raw_url):
    if not raw_url:
        return DEFAULT_SUPABASE_URL
    url = raw_url.strip().strip('"').strip("'")
    # Remove accidental square brackets around password if present
    url = url.replace(':[', ':').replace(']@', '@')
    # Automatically URL-encode raw password if needed
    if "r-THx9s8!y879SX" in url:
        url = url.replace("r-THx9s8!y879SX", DB_PASS)
    return url

DATABASE_URL = clean_db_url(os.environ.get('DATABASE_URL', DEFAULT_SUPABASE_URL))

# Indian Standard Time (IST, UTC+05:30)
tz_ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_ist_now():
    return datetime.datetime.now(tz_ist).strftime("%Y-%m-%d %H:%M:%S")


# ==============================================================================
# 🟢 SMART DUAL-ENGINE DATABASE WRAPPER (100% Zero-Error Guarantee)
# ==============================================================================
class SmartCursor:
    def __init__(self, cursor, is_pg):
        self.cursor = cursor
        self.is_pg = is_pg

    def execute(self, sql, params=None):
        if self.is_pg:
            sql_clean = sql.strip()
            if sql_clean.upper().startswith("PRAGMA"):
                return
            sql_clean = re.sub(
                r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT',
                'SERIAL PRIMARY KEY',
                sql_clean,
                flags=re.IGNORECASE
            )
            if 'INSERT OR IGNORE INTO' in sql_clean.upper():
                sql_clean = re.sub(
                    r'INSERT\s+OR\s+IGNORE\s+INTO',
                    'INSERT INTO',
                    sql_clean,
                    flags=re.IGNORECASE
                )
                sql_clean = sql_clean.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
            sql_clean = sql_clean.replace('?', '%s')
            if params is not None:
                return self.cursor.execute(sql_clean, params)
            return self.cursor.execute(sql_clean)
        else:
            if params is not None:
                return self.cursor.execute(sql, params)
            return self.cursor.execute(sql)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()


class SmartConnection:
    def __init__(self, conn, is_pg):
        self.conn = conn
        self.is_pg = is_pg

    def cursor(self):
        if self.is_pg:
            return SmartCursor(self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor), True)
        return SmartCursor(self.conn.cursor(), False)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        try:
            self.conn.rollback()
        except Exception:
            pass

    def close(self):
        self.conn.close()


# --- GLOBAL PERSISTENT SUPABASE CONNECTION (Zero-Latency) ---
_cached_pg_conn = None

def get_db():
    global _cached_pg_conn
    if HAS_PG and DATABASE_URL:
        # 1. पहले से खुले कनेक्शन को दोबारा इस्तेमाल करें (0 सेकंड लेटेंसी)
        if _cached_pg_conn is not None:
            try:
                # चेक करें कि कनेक्शन एक्टिव है या नहीं
                if _cached_pg_conn.closed == 0:
                    return SmartConnection(_cached_pg_conn, True)
            except Exception:
                _cached_pg_conn = None

        # 2. अगर कनेक्शन बंद है या पहली बार चल रहा है, तभी नया कनेक्ट करें
        try:
            _cached_pg_conn = psycopg2.connect(DATABASE_URL, sslmode='require', connect_timeout=8)
            _cached_pg_conn.autocommit = True
            return SmartConnection(_cached_pg_conn, True)
        except Exception as e:
            print(f"[Supabase Notice] Switching to local SQLite backup: {e}")
            _cached_pg_conn = None

    # 3. सुरक्षित बैकअप (अगर इंटरनेट/सुपाबेस डाउन हो तो SQLite)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return SmartConnection(conn, False)


def ensure_columns_exist(conn):
    """Self-healing migration: guarantees all columns exist on both SQLite & Supabase."""
    incident_cols = [
        ("caller_phone", "TEXT DEFAULT ''"),
        ("ticket_type", "TEXT DEFAULT 'REQ'"),
        ("subcategory", "TEXT DEFAULT ''"),
        ("priority", "TEXT DEFAULT '3 - Moderate'"),
        ("state", "TEXT DEFAULT 'New'"),
        ("assignment_group", "TEXT DEFAULT 'Thane_Rayccc_Helpdesk_Support'"),
        ("assigned_to", "TEXT DEFAULT 'Raymond Customer Competency Center'"),
        ("description", "TEXT DEFAULT ''"),
        ("attachment_name", "TEXT DEFAULT ''"),
        ("attachment_size", "TEXT DEFAULT ''"),
        ("work_notes", "TEXT DEFAULT ''"),
        ("resolution_notes", "TEXT DEFAULT ''"),
        ("updated_at", "TEXT DEFAULT ''"),
        ("updated_by", "TEXT DEFAULT 'system'")
    ]
    user_cols = [
        ("phone", "TEXT DEFAULT ''"),
        ("role", "TEXT DEFAULT 'END_USER'"),
        ("created_at", "TEXT DEFAULT ''")
    ]

    for col_name, col_def in incident_cols:
        try:
            c = conn.cursor()
            c.execute(f"ALTER TABLE incidents ADD COLUMN {col_name} {col_def}")
            conn.commit()
        except Exception:
            conn.rollback()

    for col_name, col_def in user_cols:
        try:
            c = conn.cursor()
            c.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
            conn.commit()
        except Exception:
            conn.rollback()


def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # 1. Main Incidents Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT UNIQUE NOT NULL,
            caller_name TEXT NOT NULL,
            caller_email TEXT NOT NULL,
            caller_phone TEXT DEFAULT '',
            ticket_type TEXT DEFAULT 'REQ',
            category TEXT NOT NULL,
            subcategory TEXT DEFAULT '',
            priority TEXT DEFAULT '3 - Moderate',
            state TEXT DEFAULT 'New',
            assignment_group TEXT DEFAULT 'Thane_Rayccc_Helpdesk_Support',
            assigned_to TEXT DEFAULT 'Raymond Customer Competency Center',
            short_description TEXT NOT NULL,
            description TEXT DEFAULT '',
            attachment_name TEXT DEFAULT '',
            attachment_size TEXT DEFAULT '',
            work_notes TEXT DEFAULT '',
            resolution_notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT DEFAULT '',
            updated_by TEXT DEFAULT 'system'
        )
    ''')

    # 2. Activities / Audit Trail
    c.execute('''
        CREATE TABLE IF NOT EXISTS ticket_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT NOT NULL,
            author TEXT DEFAULT 'IT Agent',
            is_internal INTEGER DEFAULT 0,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    # 3. Corporate Users Table (Authentication & RBAC)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT DEFAULT 'END_USER',
            phone TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()

    # Auto-heal any older table schemas (fixes missing caller_phone / phone columns)
    ensure_columns_exist(conn)

    # Pre-populate known Raymond corporate accounts
    try:
        initial_users = [
            ('rayccc@raymond.in', 'raymond@123', 'RAYCCC Helpdesk Engineer', 'ITIL_AGENT'),
            ('raymond.support@raymond.in', 'raymond@123', 'Remote Support Engineer', 'ITIL_AGENT'),
            ('dss.support@raymond.in', 'raymond@123', 'DSS Desk-Side Engineer', 'ITIL_AGENT'),
            ('asset.support@raymond.in', 'raymond@123', 'Asset Team Engineer', 'ITIL_AGENT'),
            ('itadmin@raymond.in', 'raymond@123', 'IT Administrator', 'ITIL_AGENT'),
            ('adarsh.shrivastava@raymond.in', 'Adarsh@12345', 'Adarsh Shrivastava', 'END_USER'),
            ('prateek.pawar@raymond.in', 'Prateek@12345', 'Prateek Pawar', 'END_USER')
        ]
        now_ist = get_ist_now()
        c = conn.cursor()
        for u_email, u_pass, u_name, u_role in initial_users:
            c.execute('''
                INSERT OR IGNORE INTO users (email, password, name, role, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (u_email, u_pass, u_name, u_role, now_ist))
        conn.commit()
    except Exception:
        conn.rollback()

    conn.close()

init_db()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

# 1. GET All Tickets
@app.route('/api/tickets', methods=['GET'])
@app.route('/api/incidents', methods=['GET'])
def get_tickets():
    bin_filter = request.args.get('bin', 'all').lower()
    conn = get_db()
    c = conn.cursor()

    if 'rayccc' in bin_filter:
        c.execute("SELECT * FROM incidents WHERE (LOWER(assignment_group) LIKE '%rayccc%' OR LOWER(assignment_group) LIKE '%thane%') AND state != 'Closed' ORDER BY id DESC")
    elif 'dss' in bin_filter:
        c.execute("SELECT * FROM incidents WHERE LOWER(assignment_group) LIKE '%dss%' AND state != 'Closed' ORDER BY id DESC")
    elif 'remote' in bin_filter:
        c.execute("SELECT * FROM incidents WHERE LOWER(assignment_group) LIKE '%remote%' AND state != 'Closed' ORDER BY id DESC")
    elif 'asset' in bin_filter:
        c.execute("SELECT * FROM incidents WHERE LOWER(assignment_group) LIKE '%asset%' AND state != 'Closed' ORDER BY id DESC")
    elif 'server' in bin_filter:
        c.execute("SELECT * FROM incidents WHERE LOWER(assignment_group) LIKE '%server%' AND state != 'Closed' ORDER BY id DESC")
    elif 'network' in bin_filter:
        c.execute("SELECT * FROM incidents WHERE LOWER(assignment_group) LIKE '%network%' AND state != 'Closed' ORDER BY id DESC")
    elif 'sap' in bin_filter or 'basis' in bin_filter:
        c.execute("SELECT * FROM incidents WHERE (LOWER(assignment_group) LIKE '%sap%' OR LOWER(assignment_group) LIKE '%basis%') AND state != 'Closed' ORDER BY id DESC")
    elif bin_filter == 'closed':
        c.execute("SELECT * FROM incidents WHERE state = 'Closed' ORDER BY id DESC")
    else:
        c.execute("SELECT * FROM incidents ORDER BY id DESC")

    rows = c.fetchall()
    tickets = [dict(row) for row in rows]
    conn.close()
    return jsonify(tickets)

# 2. GET Single Ticket (Fresh Real-Time Fetch)
@app.route('/api/tickets/<ticket_number>', methods=['GET'])
def get_single_ticket(ticket_number):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM incidents WHERE ticket_number = ?", (ticket_number,))
    row = c.fetchone()
    conn.close()
    if row:
        return jsonify(dict(row))
    return jsonify({"error": "Ticket not found"}), 404

# 3. POST Update Ticket
@app.route('/api/tickets/<ticket_number>/update', methods=['POST', 'PUT'])
@app.route('/api/tickets/<ticket_number>', methods=['POST', 'PUT'])
@app.route('/api/tickets/<ticket_number>/assign', methods=['POST'])
@app.route('/api/tickets/update', methods=['POST'])
def update_ticket(ticket_number=None):
    try:
        data = request.get_json(force=True, silent=True) or request.form.to_dict() or {}
        if not ticket_number:
            ticket_number = data.get('ticket_number')
        if not ticket_number:
            return jsonify({"success": False, "message": "Ticket number is required."}), 400

        new_state = data.get('state')
        new_group = data.get('assignment_group') or data.get('group')
        new_desc = (data.get('description') or '').strip()
        new_short = (data.get('short_description') or '').strip()
        new_phone = data.get('caller_phone')
        work_note = (data.get('work_note') or data.get('work_notes') or '').strip()
        comment = (data.get('comment') or data.get('comments') or '').strip()
        author_role = data.get('role') or data.get('user_role') or 'ITIL_AGENT'
        caller_name = data.get('caller_name') or data.get('user_name') or 'Employee'
        now_ist = get_ist_now()

        conn = get_db()
        cursor = conn.cursor()

        updates = []
        params = []

        if new_state:
            updates.append("state = ?")
            params.append(new_state)

        if new_group:
            updates.append("assignment_group = ?")
            params.append(new_group)

        if new_phone:
            updates.append("caller_phone = ?")
            params.append(new_phone)

        if new_short:
            updates.append("short_description = ?")
            params.append(new_short)

        if new_desc:
            updates.append("description = ?")
            params.append(new_desc)

        if work_note or comment:
            note_entry = f"[{now_ist}]\n"
            if work_note:
                note_entry += f"[Internal Note]: {work_note}\n"
            if comment:
                note_entry += f"[{caller_name}]: {comment}\n"
            updates.append("work_notes = COALESCE(work_notes, '') || '\n\n' || ?")
            params.append(note_entry)

        updates.append("updated_at = ?")
        params.append(now_ist)
        updates.append("updated_by = ?")
        params.append(caller_name if author_role == 'END_USER' else "ITIL Agent")

        params.append(ticket_number)
        sql = f"UPDATE incidents SET {', '.join(updates)} WHERE ticket_number = ?"
        cursor.execute(sql, params)

        if new_group:
            cursor.execute(
                "INSERT INTO ticket_activities (ticket_number, author, is_internal, message, created_at) VALUES (?, ?, 1, ?, ?)",
                (ticket_number, f"IT Agent ({caller_name})" if author_role != 'END_USER' else "Queue Router", f"Queue Transferred ➔ {new_group} Bin", now_ist)
            )

        if new_short or new_desc:
            change_details = []
            if new_short:
                change_details.append(f"Short Desc: '{new_short}'")
            if new_desc:
                change_details.append(f"Detailed Justification: '{new_desc}'")
            update_summary = "Issue updated (" + ", ".join(change_details) + ")"
            cursor.execute(
                "INSERT INTO ticket_activities (ticket_number, author, is_internal, message, created_at) VALUES (?, ?, 0, ?, ?)",
                (ticket_number, f"{caller_name} (Issue Updated)" if author_role == 'END_USER' else "IT Agent", update_summary, now_ist)
            )

        if work_note:
            author_work = f"IT Agent ({caller_name})" if author_role != 'END_USER' else "IT Agent"
            cursor.execute(
                "INSERT INTO ticket_activities (ticket_number, author, is_internal, message, created_at) VALUES (?, ?, 1, ?, ?)",
                (ticket_number, author_work, work_note, now_ist)
            )

        if comment:
            author_label = f"Client ({caller_name})" if author_role == 'END_USER' else f"IT Agent ({caller_name})"
            cursor.execute(
                "INSERT INTO ticket_activities (ticket_number, author, is_internal, message, created_at) VALUES (?, ?, 0, ?, ?)",
                (ticket_number, author_label, comment, now_ist)
            )

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": f"Ticket {ticket_number} successfully updated."
        })

    except Exception as e:
        print(f"[Update Error] {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# 4. GET Timeline
@app.route('/api/tickets/<ticket_number>/timeline', methods=['GET'])
def get_timeline(ticket_number):
    role = request.args.get('role', 'ITIL_AGENT')
    conn = get_db()
    cursor = conn.cursor()

    if role == 'END_USER':
        cursor.execute("SELECT * FROM ticket_activities WHERE ticket_number = ? AND is_internal = 0 ORDER BY id ASC", (ticket_number,))
    else:
        cursor.execute("SELECT * FROM ticket_activities WHERE ticket_number = ? ORDER BY id ASC", (ticket_number,))

    activities = [dict(row) for row in cursor.fetchall()]

    if not activities:
        cursor.execute("SELECT work_notes, created_at FROM incidents WHERE ticket_number = ?", (ticket_number,))
        inc = cursor.fetchone()
        if inc and inc['work_notes']:
            activities = [{
                "ticket_number": ticket_number,
                "author": "System Log",
                "is_internal": 0,
                "message": inc['work_notes'],
                "created_at": inc['created_at']
            }]

    conn.close()
    return jsonify(activities)

# 🟢 EMAIL ADDRESS DIRECTORY
def get_team_email(assignment_group):
    team_emails = {
        'Asset Team': 'Assest.mgmt@raymond.in',
        'Network Team': 'Ray.wan@raymond.in',
        'Remote Team': 'Remote.support@raymond.in',
        'DSS Team': 'Retail.support@raymond.in',
        'Thane_Rayccc_Helpdesk_Support': 'rayccc@raymond.in',
        'Raymond Reality Team': 'Reality.support@raymond.in'
    }
    return team_emails.get(assignment_group, 'rayccc@raymond.in')

# 🟢 CONTACT NUMBER DIRECTORY
def get_team_contact(assignment_group):
    team_contacts = {
        'Thane_Rayccc_Helpdesk_Support': '02240954966 / 4965 / 4964 / 4963',
        'Remote Team': '02240954855 / 4853',
        'Network Team': '02240367480 / 7176',
        'Server Team': '8080483438 (Bhupendra Juvatkar)<br><br>, 9702837703 (Hiraman Mhadse)<br><br>, 6002263077 (Rajkishor kumar)<br><br>',
        'Asset Team': '02240954991',
        'SAP Basis Team': 'TBA (Number will be provided later)',
        'DSS Team': 'N/A',
        'Raymond Reality Team': '02240954999'
    }
    return team_contacts.get(assignment_group, 'N/A')

# TICKET ROUTING LOGIC
def determine_assignment_group(ticket_type, category, subcategory, short_description=""):
    tt = (ticket_type or '').strip().upper()
    cat = (category or '').strip().lower()
    sub = (subcategory or '').strip().lower()

    if tt == 'CHG':
        return 'Thane_Rayccc_Helpdesk_Support'
    if tt == 'USB' or 'usb access' in sub or 'usb request' in sub:
        return 'Server Team'
    if tt == 'AR':
        return 'Asset Team'
    if 'hardware' in cat or cat == 'peripherals':
        return 'Asset Team'
    if any(h in sub for h in ['laptop', 'desktop', 'monitor', 'printer', 'scanner', 'thin client', 'ipad', 'tablet', 'mouse', 'keyboard', 'charger', 'docking station']):
        return 'Asset Team'
    if 'network' in cat or 'wi-fi' in cat or 'wifi' in cat:
        return 'Network Team'
    if any(n in sub for n in ['firewall', 'wifi', 'lan issue', 'internet connectivity', 'guest wi-fi', 'network performance', 'wan', 'switch', 'router']):
        return 'Network Team'
    if 'security' in cat:
        return 'Server Team'
    if any(s in sub for s in ['phishing', 'Spamming mails', 'malware', 'unauthorized access', 'data loss', 'compliance violation', 'vulnerability']):
        return 'Server Team'
    if 'data service' in cat or 'data services' in cat:
        return 'Server Team'
    if any(d in sub for d in ['data restore', 'file/data recovery', 'backup restore', 'restore from backup']):
        return 'Server Team'
    if 'account' in cat and 'access' in cat:
        if 'ad account unlock' in sub or 'ad password reset' in sub or 'ad unlock' in sub or 'ad reset' in sub:
            return 'Thane_Rayccc_Helpdesk_Support'
        if 'sap account unlock' in sub or 'sap password reset' in sub or 'vpn access' in sub:
            return 'Remote Team'
        if 'two factor' in sub or 'two-factor' in sub or '2fa' in sub or 'mfa' in sub or 'usb' in sub:
            return 'Server Team'
        return 'Thane_Rayccc_Helpdesk_Support'
    if 'software' in cat or 'installation' in cat:
        raycccApps = ['microsoft', 'google suit', 'google suite', 'other application', 'pdf reader', 'browser']
        if any(m in sub for m in raycccApps):
            return 'Thane_Rayccc_Helpdesk_Support'
        if 'sap' in sub or 'antivirus' in sub or 'security software' in sub or 'cortex' in sub:
            return 'Remote Team'
        return 'Thane_Rayccc_Helpdesk_Support'
    if 'email' in cat or 'collaboration' in cat:
        return 'Thane_Rayccc_Helpdesk_Support'
    if any(e in sub for e in ['outlook', 'gmail', 'calendar', 'forwarding', 'mail delivery', 'pst migration', 'shared mailbox']):
        return 'Thane_Rayccc_Helpdesk_Support'
    if 'shared drive' in cat or 'shared drives' in cat:
        return 'Thane_Rayccc_Helpdesk_Support'
    if any(s in sub for s in ['storage quota', 'shared folder']):
        return 'Thane_Rayccc_Helpdesk_Support'
    if 'sap id' in cat or 'sap basis' in cat or 'lifestyle sap' in cat:
        return 'SAP Basis Team'
    if any(sb in sub for sb in ['sap id', 'sap patch', 'sap basis', 'sap erp', 's4hana', 'basis']):
        return 'SAP Basis Team'
    if 'clearance' in cat or 'hardware return' in sub:
        return 'Asset Team'
    if 'configuration' in cat:
        return 'DSS Team'
    if any(r in cat or r in sub or r in (short_description or '').lower() for r in ['reality', 'realty', 'raymond reality']):
        return 'Raymond Reality Team'

    return 'Thane_Rayccc_Helpdesk_Support'
# ==============================================================================
# 5. POST Create Ticket (Manual Form Submission)
# ==============================================================================
@app.route('/api/tickets', methods=['POST'])
@app.route('/api/incidents', methods=['POST'])
@app.route('/api/tickets/create', methods=['POST'])
def create_ticket():
    try:
        data = request.get_json(force=True, silent=True) or request.form.to_dict() or {}
        caller_name = (data.get('caller_name') or data.get('requester_name') or 'Raymond Employee').strip()
        caller_email = (data.get('caller_email') or data.get('requester_email') or 'employee@raymond.in').strip()
        caller_phone = (data.get('caller_phone') or data.get('phone') or '').strip()
        
        raw_digits = re.sub(r'\D', '', caller_phone)
        if raw_digits.startswith('91') and len(raw_digits) == 12:
            raw_digits = raw_digits[2:]
        if not raw_digits or len(raw_digits) != 10:
            return jsonify({"success": False, "message": "वैध 10 अंकों का मोबाइल फ़ोन नंबर अनिवार्य है।"}), 400
        caller_phone = '+91 ' + raw_digits
        
        category = (data.get('category') or 'Service Request').strip()
        subcategory = (data.get('subcategory') or '').strip()
        priority = (data.get('priority') or '2 - High').strip()
        short_description = (data.get('short_description') or data.get('short_desc') or 'Service Request').strip()
        description = (data.get('description') or data.get('long_desc') or short_description).strip()
        attachment_name = (data.get('attachment_name') or '').strip()
        attachment_size = (data.get('attachment_size') or '').strip()

        incoming_type = (data.get('ticket_type') or '').strip().upper()
        if incoming_type in ['REQ', 'INC', 'AR', 'CHG', 'USB', 'DOMAIN']:
            ticket_type = incoming_type
        else:
            comb = (category + ' ' + subcategory).lower()
            service_words = ['clearance', 'installation', 'service', 'request', 'allocation', 'creation', 'setup', 'quota', 'configuration', 'sap id']
            ticket_type = 'REQ' if any(w in comb for w in service_words) else 'INC'

        assignment_group = data.get('assignment_group')
        if not assignment_group or assignment_group in ['Thane_Rayccc_Helpdesk_Support', 'undefined']:
            assignment_group = determine_assignment_group(ticket_type, category, subcategory, short_description)
        else:
            calculated_group = determine_assignment_group(ticket_type, category, subcategory, short_description)
            if calculated_group != 'Thane_Rayccc_Helpdesk_Support' or assignment_group == 'Thane_Rayccc_Helpdesk_Support':
                assignment_group = calculated_group

        group_assignees = {
            'Thane_Rayccc_Helpdesk_Support': 'RAYCCC Helpdesk Engineer',
            'Remote Team': 'Remote Support Engineer',
            'DSS Team': 'DSS Desk-Side Engineer',
            'Asset Team': 'Asset Team Engineer',
            'Server Team': 'Server Team Engineer',
            'Network Team': 'Network Team Engineer',
            'SAP Basis Team': 'SAP Basis Engineer'
        }
        assigned_to = group_assignees.get(assignment_group, 'Raymond Customer Competency Center')
        
        team_email = get_team_email(assignment_group)
        team_contact = get_team_contact(assignment_group)
        description += (
            f"\n\n[System Routing Info]\n"
            f"• Assigned Team Mail ID: {team_email}\n"
            f"• Assigned Team Contact: {team_contact}"
        )

        conn = get_db()
        #ensure_columns_exist(conn)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM incidents")
        count = c.fetchone()['cnt'] + 1
        ticket_number = f"{ticket_type}{count:06d}"

        created_at = get_ist_now()
        work_notes = f"[{created_at}] {ticket_type} Ticket raised via SmartDesk AI Portal. Automatically routed to {assignment_group} Bin based on Category: {category} | Subcategory: {subcategory}."
        if attachment_name:
            work_notes += f"\nPre-Approval Attached: {attachment_name} ({attachment_size})"

        c.execute('''
            INSERT INTO incidents (
                ticket_number, caller_name, caller_email, caller_phone,
                ticket_type, category, subcategory, priority, state,
                assignment_group, assigned_to, short_description, description,
                attachment_name, attachment_size, work_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ticket_number, caller_name, caller_email, caller_phone,
            ticket_type, category, subcategory, priority, 'New',
            assignment_group, assigned_to,
            short_description, description,
            attachment_name, attachment_size, work_notes,
            created_at, created_at
        ))

        c.execute('''
            INSERT INTO ticket_activities (ticket_number, author, is_internal, message, created_at)
            VALUES (?, 'System', 0, ?, ?)
        ''', (ticket_number, work_notes, created_at))

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "ticket_number": ticket_number,
            "ticket_type": ticket_type,
            "assignment_group": assignment_group,
            "message": f"Ticket {ticket_number} created successfully and assigned to {assignment_group}."
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ==============================================================================
# 6. GET Live Stats (Dashboard)
# ==============================================================================
@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT assignment_group, state, COUNT(*) as count FROM incidents GROUP BY assignment_group, state")
    rows = c.fetchall()
    stats = {"rayccc": 0, "dss": 0, "remote": 0, "asset": 0, "server": 0, "network": 0, "sap_basis": 0, "total": 0}
    for r in rows:
        grp = (r['assignment_group'] or '').lower()
        st = r['state']
        cnt = r['count']
        stats['total'] += cnt
        if st != 'Closed':
            if 'server' in grp:
                stats['server'] += cnt
            elif 'network' in grp:
                stats['network'] += cnt
            elif 'sap' in grp or 'basis' in grp:
                stats['sap_basis'] += cnt
            elif 'dss' in grp:
                stats['dss'] += cnt
            elif 'remote' in grp:
                stats['remote'] += cnt
            elif 'asset' in grp:
                stats['asset'] += cnt
            else:
                stats['rayccc'] += cnt
    conn.close()
    return jsonify({"success": True, "stats": stats})

# ==============================================================================
# 9. Role-Based Authentication & Auto-Registration (RBAC)
# ==============================================================================
IT_ENGINEER_ACCOUNTS = {
    'rayccc@raymond.in': {'password': 'Strong@1947', 'name': 'RAYCCC Helpdesk Engineer', 'role': 'ITIL_AGENT'},
    'remote.support@raymond.in': {'password': 'raymond@123', 'name': 'Remote Support Engineer', 'role': 'ITIL_AGENT'},
    'dss.support@raymond.in': {'password': 'raymond@123', 'name': 'DSS Desk-Side Engineer', 'role': 'ITIL_AGENT'},
    'asset.support@raymond.in': {'password': 'raymond@123', 'name': 'Asset Team Engineer', 'role': 'ITIL_AGENT'},
    'server.support@raymond.in': {'password': 'raymond@123', 'name': 'Server Team Engineer', 'role': 'ITIL_AGENT'},
    'network.support@raymond.in': {'password': 'raymond@123', 'name': 'Network Team Engineer', 'role': 'ITIL_AGENT'},
    'ray.wan@raymond.in': {'password': 'raymond@123', 'name': 'Network Team Engineer (WAN)', 'role': 'ITIL_AGENT'},
    'sapbasis.support@raymond.in': {'password': 'raymond@123', 'name': 'SAP Basis Engineer', 'role': 'ITIL_AGENT'},
    'itadmin@raymond.in': {'password': 'raymond@123', 'name': 'IT Administrator', 'role': 'ITIL_AGENT'},
    'reality.support@raymond.in': {'password': 'raymond@123', 'name': 'Raymond Reality Engineer', 'role': 'ITIL_AGENT'}
}
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json(force=True, silent=True) or {}
    raw_email = (data.get('email') or '').strip()
    email = raw_email.lower()
    password = (data.get('password') or '').strip()

    if not email:
        return jsonify({"success": False, "message": "Login Failed: Email ID दर्ज करना अनिवार्य है।"}), 400

    if not password:
        return jsonify({"success": False, "message": "Login Failed: पासवर्ड दर्ज करना अनिवार्य है।"}), 400

    if not email.endswith('@raymond.in'):
        return jsonify({
            "success": False,
            "message": "Login Failed: Invalid user ID and credential"
        }), 403

    username_part = email[:-len('@raymond.in')].strip()
    if not username_part or len(username_part) < 2 or ' ' in username_part:
        return jsonify({
            "success": False,
            "message": "Login Failed: अमान्य ईमेल फ़ॉर्मेट! कृपया सही रेमंड कॉर्पोरेट ईमेल आईडी दर्ज करें।"
        }), 400

    name_parts = username_part.split('.')
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ''
    full_display_name = f"{first_name.capitalize()} {last_name.capitalize()}".strip()

    conn = get_db()
    #ensure_columns_exist(conn)
    c = conn.cursor()

    if email in IT_ENGINEER_ACCOUNTS:
        acct = IT_ENGINEER_ACCOUNTS[email]
        valid_it_passes = [ 
            acct['password']
        ]
        if password in valid_it_passes:
            conn.close()
            return jsonify({
                "success": True,
                "role": "ITIL_AGENT",
                "email": raw_email,
                "name": acct['name'],
                "message": f"Welcome, {acct['name']}🥷🏻 In Smartdesk AI."
            })
        else:
            conn.close()
            return jsonify({
                "success": False,
                "message": "login failed, IT engineer का password गलत है।"
            }), 401

    allowed_passwords = [
        f"{first_name.capitalize()}@12345",
        f"{first_name.lower()}@12345",
        f"{first_name}@12345",
        "raymond@123",
        "Raymond@123"
    ]

    if password in allowed_passwords:
        now_ist = get_ist_now()
        c.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email,))
        row = c.fetchone()
        
        if not row:
            c.execute('''
                INSERT INTO users (email, password, name, role, created_at)
                VALUES (?, ?, ?, 'END_USER', ?)
            ''', (email, password, full_display_name, now_ist))
            conn.commit()

        conn.close()
        return jsonify({
            "success": True,
            "role": "END_USER",
            "email": raw_email,
            "name": full_display_name,
            "message": f"नमस्ते {full_display_name}! Employee Center में आपका स्वागत है।"
        })
    else:
        conn.close()
        return jsonify({
            "success": False,
            "message": "login failed, password is wrong"
        }), 401

# ==============================================================================
# 10. MULTI-AGENT AI CHATBOT & AUTONOMOUS TICKET CREATION ENGINE
# ==============================================================================
class GreetingAgent:
    name = "👋 Greeting Agent"

    @staticmethod
    def can_handle(msg_lower):
        greetings = [
            'hi', 'hello', 'hey', 'namaste', 'namaskar', 'good morning',
            'good afternoon', 'good evening', 'hii', 'helo', 'ram ram',
            'kaise ho', 'how are you', ' नमस्ते', 'हेलो', 'हाय'
        ]
        words = re.findall(r'\w+', msg_lower)
        issue_keywords = [
            'unlock', 'password', 'reset', 'issue', 'problem', 'error', 'not working',
            'slow', 'laptop', 'mouse', 'keyboard', 'bag', 'charger', 'wifi', 'wi-fi',
            'internet', 'vpn', 'sap', 'outlook', 'mail', 'email', 'excel', 'office',
            'printer', 'scanner', 'monitor', 'usb', 'pendrive', 'backup', 'restore',
            'virus', 'phishing', 'Spamming mails', 'drive', 'folder', 'quota', 'ticket', 'chahiye',
            'nhi', 'nahi', 'band', ' खराब', 'चाहिए', 'अनलॉक', 'पासवर्ड'
        ]
        if any(k in msg_lower for k in issue_keywords):
            return False
        return any(g == msg_lower.strip() or g in words for g in greetings) and len(words) <= 6

    @staticmethod
    def respond(user_name):
        return {
            "agent": GreetingAgent.name,
            "ticket_created": False,
            "reply": (
                f"<div class='greet-hi'>"
                f"नमस्ते <b>{user_name}</b>! 👋 मैं <b>SmartDesk Greeting Agent</b> हूँ。<br><br>"
                f"आपको कोई भी Ticket Manually create करने की ज़रूरत नहीं है💃🏼! बस अपनी Request/Issue यहाँ सीधे लिखें, उदाहरण के लिए:<br>"
                f"• <i>\"Please unlock my system account.\"</i><br>"
                f"• <i>\"Please reset my password.\"</i><br>"
                f"• <i>\"मुझे नया Laptop Bag या Mouse चाहिए\"</i><br>"
                f"• <i>\"Wi-Fi या VPN काम नहीं कर रहा है\"</i><br>"
                f"• <i>\"Please unlock my SAP account.\"</i><br><br>"
                f"हमारा <b>Autonomous Ticket Agent</b>😎 तुरंत आपके लिए आपकी ticket create करके सही team को assign कर देगा और हमारी support team आपसे जल्द ही connect करेगी。<br><br>"
                f"हमारे engineers को अपना सहयोग प्रदान करें। धन्यवाद।"
                f"</div>"
                f"<div class='greet-en' style='display:none;'>"
                f"Hello <b>{user_name}</b>! 👋 I am the <b>SmartDesk Greeting Agent</b>.<br><br>"
                f"You do not need to create any ticket manually💃🏼! Simply type your Request/Issue directly here, for example:<br>"
                f"• <i>\"Please unlock my system account.\"</i><br>"
                f"• <i>\"Please reset my password.\"</i><br>"
                f"• <i>\"I need a new Laptop Bag or Mouse.\"</i><br>"
                f"• <i>\"Wi-Fi or VPN is not working.\"</i><br>"
                f"• <i>\"Please unlock my SAP account.\"</i><br><br>"
                f"Our <b>Autonomous Ticket Agent</b> 🤖 will immediately create your ticket, assign it to the right team, and our support team will connect with you shortly.<br><br>"
                f"Please extend your cooperation to our engineers. Thank you."
                f"</div>"
                f"<div class='greet-mr' style='display:none;'>"
                f"नमस्ते <b>{user_name}</b>! 👋 मी <b>SmartDesk Greeting Agent</b> आहे.<br><br>"
                f"तुम्हाला कोणतेही Ticket Manually तयार करण्याची गरज नाही💃🏼! फक्त तुमची Request/Issue येथे थेट लिहा, उदाहरणासाठी:<br>"
                f"• <i>\"Please unlock my system account.\"</i><br>"
                f"• <i>\"Please reset my password.\"</i><br>"
                f"• <i>\"मला नवीन Laptop Bag किंवा Mouse हवे आहे\"</i><br>"
                f"• <i>\"Wi-Fi किंवा VPN काम करत नाही आहे\"</i><br>"
                f"• <i>\"Please unlock my SAP account.\"</i><br><br>"
                f"आमचा <b>Autonomous Ticket Agent</b> 🤖 त्वरित तुमच्यासाठी ticket create करून योग्य team कडे assign करेल आणि आमची support team तुमच्याशी लवकरच connect करेल.<br><br>"
                f"आमच्या engineers ना सहकार्य करा. धन्यवाद."
                f"</div>"
                f"<div style='margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;'>"
                f"<button class='btn-en' onclick=\"var p=this.parentElement.parentElement; var hi=p.querySelector('.greet-hi'); var en=p.querySelector('.greet-en'); var mr=p.querySelector('.greet-mr'); var bMr=p.querySelector('.btn-mr'); var toEn=en.style.display==='none'; en.style.display=toEn?'block':'none'; hi.style.display=toEn?'none':'block'; mr.style.display='none'; this.innerText=toEn?'🌐 हिंदी में देखें':'🌐 Convert to English'; bMr.innerText='🌐 Convert to Marathi';\" style='background:#2563eb;color:#ffffff;border:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:inline-block;'>🌐 Convert to English</button>"
                f"<button class='btn-mr' onclick=\"var p=this.parentElement.parentElement; var hi=p.querySelector('.greet-hi'); var en=p.querySelector('.greet-en'); var mr=p.querySelector('.greet-mr'); var bEn=p.querySelector('.btn-en'); var toMr=mr.style.display==='none'; mr.style.display=toMr?'block':'none'; hi.style.display=toMr?'none':'block'; en.style.display='none'; this.innerText=toMr?'🌐 हिंदी में देखें':'🌐 Convert to Marathi'; bEn.innerText='🌐 Convert to English';\" style='background:#059669;color:#ffffff;border:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:inline-block;'>🌐 Convert to Marathi</button>"
                f"</div>"
            )
        }

class FarewellAgent:
    name = "🙏 Farewell Agent"

    @staticmethod
    def can_handle(msg_lower):
        farewells = [
            'bye', 'goodbye', 'good bye', 'good night', 'thank you', 'thanks', 'thanku', 'thank u',
            'thx', 'shukriya', 'dhanyawad', 'dhanyavad', 'alvida',
            'ok thanks', 'ok bye', 'see you', 'धन्यवाद', 'शुक्रिया', 'बाय', 'अलविदा'
        ]
        issue_keywords = [
            'unlock', 'password', 'reset', 'issue', 'problem', 'laptop', 'wifi',
            'vpn', 'sap', 'mail', 'printer', 'usb', 'chahiye', 'nahi', 'nhi'
        ]
        if any(k in msg_lower for k in issue_keywords):
            return False
        return any(f in msg_lower for f in farewells) and len(msg_lower.split()) <= 6

    @staticmethod
    def respond(user_name):
        return {
            "agent": FarewellAgent.name,
            "ticket_created": False,
            "reply": (
                f"<div class='farewell-hi'>"
                f"आपका बहुत-बहुत धन्यवाद, <b>{user_name}</b>! 🙏<br><br>"
                f"मैं <b>SmartDesk Farewell Agent</b> हूँ। मुझे खुशी है कि हम आपकी help कर सके। भविष्य में किसी भी IT help या ticket raise के लिए कभी भी चैट करें। आपका दिन शुभ हो! ✨"
                f"</div>"
                f"<div class='farewell-en' style='display:none;'>"
                f"Thank you very much, <b>{user_name}</b>! 🙏<br><br>"
                f"I am the <b>SmartDesk Farewell Agent</b>. We are glad we could help you. Feel free to chat anytime for any future IT help or ticket raising. Have a great day! ✨"
                f"</div>"
                f"<div class='farewell-mr' style='display:none;'>"
                f"खूप खूप धन्यवाद, <b>{user_name}</b>! 🙏<br><br>"
                f"मी <b>SmartDesk Farewell Agent</b> आहे. आम्ही तुम्हाला मदत करू शकलो याचा आम्हाला आनंद आहे. भविष्यात कोणत्याही IT मदतीसाठी किंवा ticket तयार करण्यासाठी केव्हाही चॅट करा. आपला दिवस शुभ जावो! ✨"
                f"</div>"
                f"<div style='margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;'>"
                f"<button class='btn-fw-en' onclick=\"var p=this.parentElement.parentElement; var hi=p.querySelector('.farewell-hi'); var en=p.querySelector('.farewell-en'); var mr=p.querySelector('.farewell-mr'); var bMr=p.querySelector('.btn-fw-mr'); var toEn=en.style.display==='none'; en.style.display=toEn?'block':'none'; hi.style.display=toEn?'none':'block'; mr.style.display='none'; this.innerText=toEn?'🌐 हिंदी में देखें':'🌐 Convert to English'; bMr.innerText='🌐 Convert to Marathi';\" style='background:#2563eb;color:#ffffff;border:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:inline-block;'>🌐 Convert to English</button>"
                f"<button class='btn-fw-mr' onclick=\"var p=this.parentElement.parentElement; var hi=p.querySelector('.farewell-hi'); var en=p.querySelector('.farewell-en'); var mr=p.querySelector('.farewell-mr'); var bEn=p.querySelector('.btn-fw-en'); var toMr=mr.style.display==='none'; mr.style.display=toMr?'block':'none'; hi.style.display=toMr?'none':'block'; en.style.display='none'; this.innerText=toMr?'🌐 हिंदी में देखें':'🌐 Convert to Marathi'; bEn.innerText='🌐 Convert to English';\" style='background:#059669;color:#ffffff;border:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:inline-block;'>🌐 Convert to Marathi</button>"
                f"</div>"
            )
        }
class TicketStatusAgent:
    name = "🔍 Ticket Status Agent"

    @staticmethod
    def extract_ticket_number(msg):
        match = re.search(r'\b(INC|REQ|AR|USB|CHG|DOMAIN)[-\s]?\d{3,7}\b', msg.upper())
        if match:
            return match.group(0).replace(' ', '').replace('-', '')
        return None

    @staticmethod
    def can_handle(msg_lower, raw_msg):
        if TicketStatusAgent.extract_ticket_number(raw_msg):
            return True
        status_phrases = ['ticket status', 'mera ticket', 'check status', 'status kya hai', 'टिकट स्टेटस']
        return any(p in msg_lower for p in status_phrases)

    @staticmethod
    def respond(raw_msg, user_email):
        t_num = TicketStatusAgent.extract_ticket_number(raw_msg)
        conn = get_db()
        c = conn.cursor()
        if t_num:
            c.execute("SELECT * FROM incidents WHERE UPPER(REPLACE(ticket_number, '-', '')) = ?", (t_num,))
        else:
            c.execute("SELECT * FROM incidents WHERE LOWER(caller_email) = ? ORDER BY id DESC LIMIT 1", (user_email.lower(),))
        row = c.fetchone()
        conn.close()

        if not row:
            return {
                "agent": TicketStatusAgent.name,
                "ticket_created": False,
                "reply": "⚠️ हमें इस नंबर का कोई टिकट नहीं मिला। कृपया सही टिकट नंबर (जैसे <b>INC000001</b>) लिखें या नया टिकट बनाने के लिए अपनी समस्या बताएं।"
            }

        t = dict(row)
        return {
            "agent": TicketStatusAgent.name,
            "ticket_created": False,
            "ticket": t,
            "reply": (
                f"📋 <b>लाइव टिकट स्टेटस ({t['ticket_number']}):</b>\n"
                f"• <b>Status:</b> {t['state']}\n"
                f"• <b>Category:</b> {t['category']} ➔ {t['subcategory']}\n"
                f"• <b>Short Description:</b> {t['short_description']}\n"
                f"• <b>Assigned Team Bin:</b> {t['assignment_group']}\n"
                f"• <b>Created (IST):</b> {t['created_at']}"
            )
        }

class AutonomousTicketAgent:
    name = "⚡ Autonomous Ticket Agent"

    @staticmethod
    def classify_request(msg):
        m = (msg or '').lower().strip()

        if any(w in m for w in ['password reset', 'system password', 'account password', 'reset password', 'forgot password', 'password', 'reset', 'passward', 'पासवर्ड']):
            return ('REQ', 'Account & Access', 'AD Password Reset', '2 - High', f"AD Password Reset Request: {msg[:55]}")

        if any(w in m for w in ['unlock', 'system unlock', 'account unlock', 'id unlock', 'account lock', 'id lock', 'अकाउंट अनलॉक', 'आईडी अनलॉक', 'लॉक हो']):
            return ('INC', 'Account & Access', 'AD Account Unlock', '2 - High', f"AD Account / ID Unlock: {msg[:55]}")

        if any(w in m for w in ['usb', 'pendrive', 'pen drive', 'flash drive', 'पेनड्राइव']):
            return ('USB_FORM', 'Security', 'USB Access Request', '2 - High', 'USB Form Trigger')

        if any(w in m for w in ['domain login', 'onboarding', 'new joiner', 'employee account', 'new employee id', 'consultant access', 'domain form']):
            return ('DOMAIN_FORM', 'Account & Access', 'Domain Login Form', '2 - High', 'Domain Form Trigger')

        if any(w in m for w in ['sap id', 'new sap', 'sap account', 'sap access', 'transfer sap', 'sap basis', 'sap login']):
            return ('REQ', 'SAP Basis', 'SAP ID Provisioning & Access', '2 - High', f"SAP Service Request: {msg[:55]}")

        if any(w in m for w in ['shared drive', 'shared folder', 'drive access', 'folder creation', 'storage quota', 'increase quota']):
            return ('REQ', 'Shared Drives', 'Access to Shared Drive', '3 - Moderate', f"Shared Drive Access Request: {msg[:55]}")

        if any(w in m for w in ['laptop config', 'laptop configuration', 'system setup', 'configure laptop', 'laptop setup']):
            return ('REQ', 'Configuration', 'Laptop Configuration', '2 - High', f"Laptop Configuration Request: {msg[:55]}")

        if any(w in m for w in ['mail delivery', 'delivery issue', 'mail sending', 'email sending', 'sending issue', 'mail send', 'email delivery', 'delivery mailing', 'mail receive', 'email receive', 'mail/email not working', 'outlook issue', 'mail recieving issue','Group ID mail sending/receiving issue']):
            return ('INC', 'Email & Collaboration', 'Mail Delivery Issues', '2 - High', f"Mail Delivery Issue: {msg[:55]}")

        if any(w in m for w in ['email forwarding', 'forwarding', 'distribution list', 'shared mailbox', 'pst migration', 'email id creation']):
            return ('REQ', 'Email & Collaboration', 'Email Forwarding/Distribution List', '3 - Moderate', f"Email Service Request: {msg[:55]}")

        if any(w in m for w in ['excel', 'word', 'powerpoint', 'ms office', 'microsoft office', 'pdf reader', 'pdf reader access', 'software install']):
            return ('REQ', 'Software Installation', 'Microsoft Office Installation/Issue', '2 - High', f"Software / Office Requisition: {msg[:50]}")

        if any(w in m for w in ['2fa', 'mfa', 'two factor', 'two-factor', 'authenticator', 'otp']):
            return ('INC', 'Account & Access', 'Two Factor Authentication', '2 - High', f"2FA / MFA Authentication Issue: {msg[:55]}")

        if any(w in m for w in ['vpn', 'global protect', 'globalprotect']):
            return ('INC', 'Network', 'Global Protect VPN', '2 - High', f"VPN Connectivity Issue: {msg[:55]}")
        if any(w in m for w in ['wifi', 'wi-fi', 'lan', 'internet', 'network', 'net nahi', 'net slow', 'इंटरनेट', 'वाईफाई']):
            return ('INC', 'Network', 'Wifi/Lan Issue', '2 - High', f"Network / Wi-Fi Connectivity Issue: {msg[:55]}")

        if any(w in m for w in ['bag', 'laptop bag', 'backpack', 'बैग']):
            return ('AR', 'Peripherals', 'Bag', '3 - Moderate', f"Asset Requisition: Laptop Bag ({msg[:45]})")
        if any(w in m for w in ['charger', 'adapter', 'power adapter', 'चार्जर']):
            return ('AR', 'Peripherals', 'Power Adapter/Laptop Charger', '2 - High', f"Asset Requisition: Laptop Charger ({msg[:45]})")
        if any(w in m for w in ['mouse', 'माउस']):
            return ('AR', 'Peripherals', 'Wireless Mouse', '3 - Moderate', f"Asset Requisition: Mouse ({msg[:45]})")
        if any(w in m for w in ['keyboard', 'कीबोर्ड']):
            return ('AR', 'Peripherals', 'Wireless Keyboard/Mouse', '3 - Moderate', f"Asset Requisition: Keyboard ({msg[:45]})")

        if any(w in m for w in ['printer', 'print', 'प्रिंटर']):
            return ('INC', 'Hardware', 'Printer', '2 - High', f"Printer Issue / Support: {msg[:55]}")
        if any(w in m for w in ['monitor', 'screen', 'display', 'मॉनिटर', 'स्क्रीन']):
            return ('INC', 'Hardware', 'Monitor', '2 - High', f"Monitor / Display Issue: {msg[:55]}")
        if any(w in m for w in ['laptop', 'hang', 'slow', 'reboot', 'लैपटॉप']):
            return ('INC', 'Hardware', 'Laptop', '2 - High', f"Laptop Hardware / OS Issue: {msg[:55]}")

        if 'data service' in m or any(w in m for w in ['backup', 'restore', 'recovery', 'data restore', 'file recovery']):
            return ('REQ', 'Data Services', 'Data Restore from Backup', '2 - High', f"Data Services Request: {msg[:55]}")

        if any(w in m for w in ['phishing', 'Spamming mails','malware', 'security violation', 'data loss', 'vulnerability', 'compliance']):
            return ('INC', 'Security', 'Malware Infection', '1 - Critical', f"Security Incident: {msg[:55]}")

        if any(w in m for w in ['order management', 'inventory', 'billing error', 'stock issue', 'batch processing']):
            return ('REQ', 'Lifestyle SAP - Apparel', 'Order Management', '2 - High', f"SAP Apparel Request: {msg[:55]}")

        if 'clearance' in m or 'hardware return' in m or 'exit' in m:
            return ('REQ', 'IT Clearance', 'Exit Employee IT Clearance', '2 - High', f"IT Clearance Request: {msg[:55]}")
        # Raymond Reality Request
        if any(w in m for w in ['reality', 'realty', 'real estate', 'property']):
            return ('REQ', 'Reality Services', 'General Request', '2 - High', f"Raymond Reality Support: {msg[:55]}")
        return (None, None, None, None, None)

    @staticmethod
    def create_ticket_autonomously(msg, user_name, user_email, user_phone):
        res = AutonomousTicketAgent.classify_request(msg)
        if not res[0]:
            return {
                "agent": AutonomousTicketAgent.name,
                "ticket_created": False,
                "reply": (
                    f"<div class='inv-hi'>"
                    f"⚠️ <b>(Invalid IT Request):</b><br><br>"
                    f"क्षमा करें, आपका संदेश किसी भी Valid IT Category या Service catalog Item से मेल नहीं खाता है।<br><br>"
                    f"↪️ कृपया केवल Problem से संबंधित Keywords ही लिखें (उदाहरण: account unlock, password reset, mail receiving/sending issue, laptop not working, require laptop bag, आदि)।<br><br>"
                    f"<b>चिंता न करें😊</b>, आप अपना टिकट मैन्युअल रूप से (manually) भी बना सकते हैं 🎯।"
                    f"</div>"
                    f"<div class='inv-en' style='display:none;'>"
                    f"⚠️ <b>Invalid IT Request:</b><br><br>"
                    f"Sorry, your message does not correspond to any valid IT category or service catalog item.<br><br>"
                    f"↪️ Write only issue-related keywords (ex: account unlock/password reset, mail receiving/sending issue, laptop not working, require laptop bag, etc).<br><br>"
                    f"Don't worry 😊, you can also create your ticket manually 🎯."
                    f"</div>"
                    f"<div class='inv-mr' style='display:none;'>"
                    f"⚠️ <b>अवैध आयटी विनंती (Invalid IT Request):</b><br><br>"
                    f"क्षमस्व, तुमचा संदेश कोणत्याही वैध IT श्रेणी किंवा सर्व्हिस कॅटलॉग आयटमशी जुळत नाही.<br><br>"
                    f"↪️ कृपया फक्त समस्येशी संबंधित कीवर्ड लिहा (उदा: account unlock/password reset, mail receiving/sending issue, laptop not working, require laptop bag, इ.).<br><br>"
                    f"काळजी करू नका 😊, तुम्ही तुमचे तिकीट स्वतःहून (manually) देखील तयार करू शकता 🎯."
                    f"</div>"
                    f"<div style='margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;'>"
                    f"<button class='btn-inv-en' onclick=\"var p=this.parentElement.parentElement; var hi=p.querySelector('.inv-hi'); var en=p.querySelector('.inv-en'); var mr=p.querySelector('.inv-mr'); var bMr=p.querySelector('.btn-inv-mr'); var toEn=en.style.display==='none'; en.style.display=toEn?'block':'none'; hi.style.display=toEn?'none':'block'; mr.style.display='none'; this.innerText=toEn?'🌐 हिंदी में देखें':'🌐 Convert to English'; bMr.innerText='🌐 Convert to Marathi';\" style='background:#2563eb;color:#ffffff;border:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:inline-block;'>🌐 Convert to English</button>"
                    f"<button class='btn-inv-mr' onclick=\"var p=this.parentElement.parentElement; var hi=p.querySelector('.inv-hi'); var en=p.querySelector('.inv-en'); var mr=p.querySelector('.inv-mr'); var bEn=p.querySelector('.btn-inv-en'); var toMr=mr.style.display==='none'; mr.style.display=toMr?'block':'none'; hi.style.display=toMr?'none':'block'; en.style.display='none'; this.innerText=toMr?'🌐 हिंदी में देखें':'🌐 Convert to Marathi'; bEn.innerText='🌐 Convert to English';\" style='background:#059669;color:#ffffff;border:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;display:inline-block;'>🌐 Convert to Marathi</button>"
                    f"</div>"
                )
            }
        ticket_type, category, subcategory, priority, short_desc = res
        
        if ticket_type == 'USB_FORM':
            return {
                "agent": AutonomousTicketAgent.name,
                "ticket_created": False,
                "reply": "⚠️ <b>Security Policy Alert:</b><br>USB Access के लिए सीधे चैटबॉट से टिकट नहीं बनाया जा सकता। कृपया अपनी पूरी जानकारी और Approver details के साथ फॉर्म भरें。<br><br><button type='button' onclick='openUSBModal()' class='mt-2 px-4 py-2 bg-amber-500 hover:bg-amber-400 text-slate-900 rounded-lg font-bold text-xs shadow-md transition'><i class='fa-solid fa-usb mr-1'></i> Open USB Request Form</button>"
            }

        if ticket_type == 'DOMAIN_FORM':
            return {
                "agent": AutonomousTicketAgent.name,
                "ticket_created": False,
                "reply": "⚠️ <b>Policy Alert:</b><br>Domain Login या नए अकाउंट के लिए सीधे चैटबॉट से टिकट नहीं बनाया जा सकता। कृपया नीचे दिए गए फॉर्म को पूरा भरें。<br><br><button type='button' onclick='openDomainLoginModal()' class='mt-2 px-4 py-2 bg-indigo-500 hover:bg-indigo-400 text-white rounded-lg font-bold text-xs shadow-md transition'><i class='fa-solid fa-user-plus mr-1'></i> Open Domain Login Form</button>"
            }

        assignment_group = determine_assignment_group(ticket_type, category, subcategory, short_desc)

        group_assignees = {
            'Thane_Rayccc_Helpdesk_Support': 'RAYCCC Helpdesk Engineer',
            'Remote Team': 'Remote Support Engineer',
            'DSS Team': 'DSS Desk-Side Engineer',
            'Asset Team': 'Asset Team Engineer',
            'Server Team': 'Server Team Engineer',
            'Network Team': 'Network Team Engineer',
            'SAP Basis Team': 'SAP Basis Engineer'
        }
        assigned_to = group_assignees.get(assignment_group, 'Raymond Customer Competency Center')
        
        team_email = get_team_email(assignment_group)
        team_contact = get_team_contact(assignment_group)

        conn = get_db()
       #ensure_columns_exist(conn)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM incidents")
        count = c.fetchone()['cnt'] + 1
        
        ticket_number = f"{ticket_type}{count:06d}"
        created_at = get_ist_now()
        
        full_description = (
            f"[Autonomous Multi-Agent Chatbot Ticket]\n"
            f"• Raised By: {user_name} ({user_email})\n"
            f"• Contact Phone: {user_phone}\n"
            f"• User Message: \"{msg}\"\n"
            f"• Auto-Classified Category: {category} ➔ {subcategory}\n"
            f"• Routed Queue (Bin): {assignment_group} ({assigned_to})\n"
            f"• Assigned Team Mail ID: {team_email}\n"
            f"• Assigned Team Contact: {team_contact}"
        )

        work_notes = (
            f"[{created_at}] {ticket_type} Ticket autonomously raised by SmartDesk Multi-Agent AI Chatbot. "
            f"Auto-routed to {assignment_group} Bin (Category: {category} | Subcategory: {subcategory})."
        )

        c.execute('''
            INSERT INTO incidents (
                ticket_number, caller_name, caller_email, caller_phone,
                ticket_type, category, subcategory, priority, state,
                assignment_group, assigned_to, short_description, description,
                attachment_name, attachment_size, work_notes, created_at, updated_at, updated_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ticket_number, user_name, user_email, user_phone,
            ticket_type, category, subcategory, priority, 'New',
            assignment_group, assigned_to, short_desc[:70], full_description,
            '', '', work_notes, created_at, created_at, 'Autonomous AI Agent'
        ))

        c.execute('''
            INSERT INTO ticket_activities (ticket_number, author, is_internal, message, created_at)
            VALUES (?, ?, 0, ?, ?)
        ''', (ticket_number, 'SmartDesk Autonomous Ticket Agent', work_notes, created_at))

        conn.commit()
        conn.close()

        ticket_details = {
            "ticket_number": ticket_number,
            "ticket_type": ticket_type,
            "caller_name": user_name,
            "caller_email": user_email,
            "caller_phone": user_phone,
            "category": category,
            "subcategory": subcategory,
            "priority": priority,
            "state": "New",
            "assignment_group": assignment_group,
            "assigned_to": assigned_to,
            "short_description": short_desc[:70],
            "description": full_description,
            "created_at": created_at
        }

        reply_html = (
            f"✅ <b>आपका टिकट सफलतापूर्वक अपने-आप (Automatically) रेज़ हो गया है!</b>\n\n"
            f"🎫 <b>Ticket Number:</b> <span class='text-amber-300 font-bold'>{ticket_number}</span>\n"
            f"📂 <b>Category:</b> {category}\n"
            f"🔖 <b>Subcategory:</b> {subcategory}\n"
            f"⚡ <b>Priority:</b> {priority} | <b>Status:</b> New\n"
            f"🏢 <b>Assigned Bin (Queue):</b> <span class='text-emerald-300 font-semibold'>{assignment_group}</span>\n"
            f"👨‍💻 <b>Assigned Engineer:</b> {assigned_to}\n"
            f"🕒 <b>Created (IST):</b> {created_at}\n\n"
            f"यह टिकट IT Engineer के <b>'{assignment_group}'</b> बिन में लाइव अपडेट हो चुका है। <b>'Open Ticket'</b> पर क्लिक करके ticket में changes भी कर सकते हैं।"
        )

        return {
            "agent": AutonomousTicketAgent.name,
            "ticket_created": True,
            "ticket": ticket_details,
            "reply": reply_html
        }


class OrchestratorAgent:
    @staticmethod
    def process(message, user_name, user_email, user_phone):
        msg_clean = (message or '').strip()
        msg_lower = msg_clean.lower()

        if GreetingAgent.can_handle(msg_lower):
            return GreetingAgent.respond(user_name)

        if FarewellAgent.can_handle(msg_lower):
            return FarewellAgent.respond(user_name)

        if TicketStatusAgent.can_handle(msg_lower, msg_clean):
            return TicketStatusAgent.respond(msg_clean, user_email)

        return AutonomousTicketAgent.create_ticket_autonomously(msg_clean, user_name, user_email, user_phone)


@app.route('/api/chatbot', methods=['POST'])
def chatbot_endpoint():
    try:
        data = request.get_json(force=True, silent=True) or {}
        message = (data.get('message') or '').strip()
        user_name = (data.get('name') or 'Adarsh Shrivastava').strip()
        user_email = (data.get('email') or 'adarsh.shrivastava@raymond.in').strip()

        if not message:
            return jsonify({
                "agent": GreetingAgent.name,
                "ticket_created": False,
                "reply": "कृपया अपनी समस्या या प्रश्न लिखें।"
            })

        conn = get_db()
        #ensure_columns_exist(conn)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?", (user_email.lower(),))
        user_row = cursor.fetchone()
        user_dict = dict(user_row) if user_row else {}
        db_phone = user_dict.get('phone') or ''
        
        req_phone = (data.get('phone') or '').strip()
        saved_phone = db_phone or req_phone
        
        raw_digits = re.sub(r'\D', '', saved_phone)
        if raw_digits.startswith('91') and len(raw_digits) == 12:
            raw_digits = raw_digits[2:]
        valid_phone = ('+91 ' + raw_digits) if len(raw_digits) == 10 else ''

        msg_digits = re.sub(r'\D', '', message)
        if msg_digits.startswith('91') and len(msg_digits) == 12:
            msg_digits = msg_digits[2:]

        if len(msg_digits) == 10:
            valid_phone = '+91 ' + msg_digits
            if not user_row:
                now_ist = get_ist_now()
                cursor.execute(
                    "INSERT OR IGNORE INTO users (email, password, name, role, phone, created_at) VALUES (?, ?, ?, 'END_USER', ?, ?)",
                    (user_email.lower(), 'raymond@123', user_name, valid_phone, now_ist)
                )
            else:
                cursor.execute("UPDATE users SET phone = ? WHERE LOWER(email) = ?", (valid_phone, user_email.lower()))
            conn.commit()
            conn.close()
            return jsonify({
                "agent": "📱 Phone Verification Agent",
                "ticket_created": False,
                "reply": f"धन्यवाद <b>{user_name}</b>! आपका मोबाइल नंबर <b>{valid_phone}</b> सफलतापूर्वक सुरक्षित कर लिया गया है। ✅<br><br>अब आप अपनी कोई भी IT Issue या Service Request यहाँ लिख सकते हैं, और मैं तुरंत आपका टिकट बना दूँगी।"
            })

        if not valid_phone:
            conn.close()
            return jsonify({
                "agent": "📱 Phone Verification Agent",
                "ticket_created": False,
                "reply": (
                    f"नमस्ते <b>{user_name}</b>! 🙏<br><br>"
                    f"Ticket बनाने से पहले आपका <b>10 digits का contact mobile number</b> होना आवश्यक है ताकि IT Engineer आवश्यकता पड़ने पर आपसे तुरंत contact कर सकें।<br><br>"
                    f"कृपया अपना <b> 10 digits का mobile number</b> यहाँ chat में enter करें (Example: <i>9966996669</i>):"
                )
            })

        conn.close()

        result = OrchestratorAgent.process(message, user_name, user_email, valid_phone)
        return jsonify(result)
    except Exception as e:
        print(f"[Multi-Agent Chatbot Error] {e}")
        return jsonify({
            "agent": "⚠️ System Agent",
            "ticket_created": False,
            "reply": f"क्षमा करें, अनुरोध प्रोसेस करने में त्रुटि हुई: {str(e)}"
        }), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
