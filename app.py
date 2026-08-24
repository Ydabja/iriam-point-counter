from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect('points.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  amount INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # アーカイブ保存用テーブル（開始日・終了日も管理）
    c.execute('''CREATE TABLE IF NOT EXISTS archives
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  period_label TEXT,
                  start_date TEXT,
                  end_date TEXT,
                  total_points INTEGER,
                  archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # 既存テーブルの拡張（存在しない場合のみカラム追加）
    try:
        c.execute('ALTER TABLE archives ADD COLUMN start_date TEXT')
        c.execute('ALTER TABLE archives ADD COLUMN end_date TEXT')
    except:
        pass

    c.execute('SELECT value FROM settings WHERE key = "week_start_date"')
    if not c.fetchone():
        today_str = datetime.now().strftime('%Y-%m-%d')
        c.execute('INSERT INTO settings (key, value) VALUES ("week_start_date", ?)', (today_str,))
    
    c.execute('SELECT value FROM settings WHERE key = "target_points"')
    if not c.fetchone():
        c.execute('INSERT INTO settings (key, value) VALUES ("target_points", "50000")')
        
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/settings/week_start', methods=['POST'])
def week_start_setting():
    conn = get_db()
    c = conn.cursor()
    data = request.get_json()
    new_date_str = data.get('start_date')
    
    if new_date_str:
        # 現在の週設定を取得
        c.execute('SELECT value FROM settings WHERE key = "week_start_date"')
        row = c.fetchone()
        old_start_str = row['value'] if row else None

        # 前の週のデータが存在する場合は自動アーカイブ
        if old_start_str and old_start_str != new_date_str:
            try:
                old_start_dt = datetime.strptime(old_start_str, '%Y-%m-%d')
                old_end_dt = old_start_dt + timedelta(days=6)
                old_end_str = old_end_dt.strftime('%Y-%m-%d')

                c.execute('''SELECT SUM(amount) FROM logs 
                             WHERE created_at >= ? AND created_at <= ?''',
                          (old_start_str + " 00:00:00", old_end_str + " 23:59:59"))
                sum_row = c.fetchone()
                old_total = sum_row[0] if sum_row and sum_row[0] is not None else 0

                period_label = f"{old_start_dt.strftime('%Y/%m/%d')} 〜 {old_end_dt.strftime('%Y/%m/%d')}"
                c.execute('INSERT INTO archives (period_label, start_date, end_date, total_points) VALUES (?, ?, ?, ?)',
                          (period_label, old_start_str, old_end_str, old_total))
            except Exception as e:
                print("Auto Archive Error:", e)

        # 新しい週の開始日を保存
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("week_start_date", ?)', (new_date_str,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
        
    conn.close()
    return jsonify({'status': 'error'}), 400

@app.route('/settings/target_points', methods=['POST'])
def target_points_setting():
    conn = get_db()
    c = conn.cursor()
    data = request.get_json()
    target_val = str(data.get('target', 0))
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("target_points", ?)', (target_val,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/archive_current_week', methods=['POST'])
def archive_current_week():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT value FROM settings WHERE key = "week_start_date"')
    row = c.fetchone()
    base_start_str = row['value'] if row else datetime.now().strftime('%Y-%m-%d')
    
    try:
        start_dt = datetime.strptime(base_start_str, '%Y-%m-%d')
    except:
        start_dt = datetime.now()
        
    end_dt = start_dt + timedelta(days=6)
    end_str = end_dt.strftime('%Y-%m-%d')
    
    c.execute('''SELECT SUM(amount) FROM logs 
                 WHERE created_at >= ? AND created_at <= ?''', 
              (base_start_str + " 00:00:00", end_str + " 23:59:59"))
    sum_row = c.fetchone()
    current_total = sum_row[0] if sum_row and sum_row[0] is not None else 0
    
    period_label = f"{start_dt.strftime('%Y/%m/%d')} 〜 {end_dt.strftime('%Y/%m/%d')}"
    
    c.execute('INSERT INTO archives (period_label, start_date, end_date, total_points) VALUES (?, ?, ?, ?)', 
              (period_label, base_start_str, end_str, current_total))
    
    # 手動アーカイブ時は翌週の開始日へ移行
    next_week_start = (start_dt + timedelta(days=7)).strftime('%Y-%m-%d')
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("week_start_date", ?)', (next_week_start,))
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/add_point', methods=['POST'])
def add_point():
    data = request.get_json()
    amount = data.get('amount', 0)
    target_date_str = data.get('target_date')
    
    if amount != 0:
        conn = get_db()
        c = conn.cursor()
        if target_date_str:
            created_at = f"{target_date_str} 12:00:00"
            c.execute('INSERT INTO logs (amount, created_at) VALUES (?, ?)', (amount, created_at))
        else:
            c.execute('INSERT INTO logs (amount) VALUES (?)', (amount,))
        conn.commit()
        conn.close()
    return jsonify({'status': 'success'})

@app.route('/get_summary')
def get_summary():
    conn = get_db()
    c = conn.cursor()

    c.execute('SELECT value FROM settings WHERE key = "week_start_date"')
    row = c.fetchone()
    base_start_str = row['value'] if row else datetime.now().strftime('%Y-%m-%d')

    c.execute('SELECT value FROM settings WHERE key = "target_points"')
    t_row = c.fetchone()
    target_points = int(t_row['value']) if t_row and t_row['value'].isdigit() else 50000
    
    try:
        current_week_start = datetime.strptime(base_start_str, '%Y-%m-%d')
    except:
        current_week_start = datetime.now()

    current_week_start_str = current_week_start.strftime('%Y-%m-%d')
    week_end = current_week_start + timedelta(days=7)
    today_str = datetime.now().strftime('%Y-%m-%d')

    daily_breakdown = []
    week_total = 0

    for i in range(7):
        day_start = current_week_start + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        
        c.execute('''SELECT SUM(amount) FROM logs 
                     WHERE created_at >= ? AND created_at < ?''',
                  (day_start.strftime('%Y-%m-%d 00:00:00'), day_end.strftime('%Y-%m-%d 00:00:00')))
        d_row = c.fetchone()
        d_total = d_row[0] if d_row and d_row[0] is not None else 0
        week_total += d_total

        day_str = day_start.strftime('%Y-%m-%d')
        daily_breakdown.append({
            'date_label': day_start.strftime('%m/%d'),
            'full_date': day_str,
            'total': d_total,
            'is_today': day_str == today_str
        })

    c.execute('SELECT SUM(amount) FROM logs')
    row_total = c.fetchone()
    total_all = row_total[0] if row_total and row_total[0] is not None else 0

    c.execute('''SELECT id, amount, created_at 
                 FROM logs 
                 WHERE created_at >= ? AND created_at < ? 
                 ORDER BY id DESC LIMIT 5''',
              (current_week_start.strftime('%Y-%m-%d 00:00:00'), week_end.strftime('%Y-%m-%d 00:00:00')))
    logs = [{'id': r['id'], 'amount': r['amount'], 'time': str(r['created_at'])} for r in c.fetchall()]

    conn.close()

    period_label = f"{current_week_start.strftime('%Y/%m/%d')}〜{(week_end - timedelta(days=1)).strftime('%m/%d')}"

    return jsonify({
        'week_start_date': current_week_start_str,
        'period_label': period_label,
        'week_total': week_total,
        'total_all': total_all,
        'target_points': target_points,
        'daily_breakdown': daily_breakdown,
        'today_str': today_str,
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
    return jsonify({'status': 'error'}), 400

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
    c.execute('SELECT id, period_label, start_date, end_date, total_points FROM archives ORDER BY id DESC')
    archives_rows = c.fetchall()

    result = []
    for r in archives_rows:
        start_date_str = r['start_date']
        daily_details = []
        
        # 期間内の日別内訳を計算
        if start_date_str:
            try:
                s_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
                for i in range(7):
                    d_start = s_dt + timedelta(days=i)
                    d_end = d_start + timedelta(days=1)
                    c.execute('''SELECT SUM(amount) FROM logs 
                                 WHERE created_at >= ? AND created_at < ?''',
                              (d_start.strftime('%Y-%m-%d 00:00:00'), d_end.strftime('%Y-%m-%d 00:00:00')))
                    d_row = c.fetchone()
                    d_tot = d_row[0] if d_row and d_row[0] is not None else 0
                    daily_details.append({
                        'date_label': d_start.strftime('%m/%d'),
                        'total': d_tot
                    })
            except Exception as e:
                print(e)

        result.append({
            'id': r['id'],
            'label': r['period_label'],
            'total': r['total_points'],
            'daily_details': daily_details
        })

    conn.close()
    return jsonify({'archives': result})

@app.route('/delete_archive', methods=['POST'])
def delete_archive():
    data = request.get_json()
    archive_id = data.get('id')
    if archive_id:
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM archives WHERE id = ?', (archive_id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
