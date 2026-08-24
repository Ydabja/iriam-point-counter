from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('points.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  amount INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('points.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_period_dates(now):
    start = now - timedelta(days=now.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add_point', methods=['POST'])
def add_point():
    data = request.get_json()
    amount = data.get('amount', 0)
    if amount > 0:
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO logs (amount) VALUES (?)', (amount,))
        conn.commit()
        conn.close()
    return jsonify({'status': 'success'})

@app.route('/get_summary')
def get_summary():
    conn = get_db()
    c = conn.cursor()
    
    now = datetime.now()
    week_start, week_end = get_period_dates(now)

    c.execute('SELECT SUM(amount) FROM logs WHERE created_at >= ? AND created_at < ?',
              (week_start.strftime('%Y-%m-%d %H:%M:%S'), week_end.strftime('%Y-%m-%d %H:%M:%S')))
    row = c.fetchone()
    current_week_total = row[0] if row[0] is not None else 0

    c.execute('SELECT SUM(amount) FROM logs')
    row_total = c.fetchone()
    total_all = row_total[0] if row_total[0] is not None else 0

    c.execute('SELECT id, amount, datetime(created_at, "+9 hours") as local_time FROM logs ORDER BY id DESC LIMIT 5')
    logs = [{'id': r['id'], 'amount': r['amount'], 'time': r['local_time']} for r in c.fetchall()]

    conn.close()

    period_label = f"{week_start.strftime('%m/%d')}〜{ (week_end - timedelta(days=1)).strftime('%m/%d') }"

    return jsonify({
        'current_week_total': current_week_total,
        'total_all': total_all,
        'current_period_label': period_label,
        'recent_logs': logs
    })

@app.route('/undo_last', methods=['POST'])
def undo_last():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM logs ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    if row:
        c.execute('DELETE FROM logs WHERE id = ?', (row['id'],))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    conn.close()
    return jsonify({'status': 'error', 'message': 'No logs'}), 400

@app.route('/delete_log', methods=['POST'])
def delete_log():
    data = request.get_json()
    log_id = data.get('id')
    if log_id:
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM logs WHERE id = ?', (log_id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/get_past_periods')
def get_past_periods():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT amount, created_at FROM logs ORDER BY created_at ASC')
    rows = c.fetchall()
    conn.close()

    periods = {}
    for r in rows:
        dt = datetime.strptime(r['created_at'], '%Y-%m-%d %H:%M:%S')
        start, end = get_period_dates(dt)
        label = f"{start.strftime('%Y/%m/%d')}〜{(end - timedelta(days=1)).strftime('%m/%d')}"
        periods[label] = periods.get(label, 0) + r['amount']

    result = [{'label': k, 'total': v} for k, v in reversed(list(periods.items()))]
    return jsonify({'periods': result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
