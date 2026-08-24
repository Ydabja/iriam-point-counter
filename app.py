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
    # ログデータ（加算日時を保持）
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  amount INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    # 設定した週の管理テーブル
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # 初回起動時にデフォルトの週開始日（今日）をセット
    c.execute('SELECT value FROM settings WHERE key = "week_start_date"')
    if not c.fetchone():
        today_str = datetime.now().strftime('%Y-%m-%d')
        c.execute('INSERT INTO settings (key, value) VALUES ("week_start_date", ?)', (today_str,))
    
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

# 週の開始日を設定・取得
@app.route('/settings/week_start', methods=['GET', 'POST'])
def week_start_setting():
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        data = request.get_json()
        new_date = data.get('start_date')
        if new_date:
            c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("week_start_date", ?)', (new_date,))
            conn.commit()
            conn.close()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error'}), 400
    else:
        c.execute('SELECT value FROM settings WHERE key = "week_start_date"')
        row = c.fetchone()
        conn.close()
        return jsonify({'start_date': row['value'] if row else datetime.now().strftime('%Y-%m-%d')})

# ポイント追加（日付が変わったら自動的にその日の0:00以降として記録）
@app.route('/add_point', methods=['POST'])
def add_point():
    data = request.get_json()
    amount = data.get('amount', 0)
    target_date_str = data.get('target_date') # YYYY-MM-DD
    
    if amount > 0:
        conn = get_db()
        c = conn.cursor()
        if target_date_str:
            # 指定日時の昼12時として登録
            created_at = f"{target_date_str} 12:00:00"
            c.execute('INSERT INTO logs (amount, created_at) VALUES (?, ?)', (amount, created_at))
        else:
            c.execute('INSERT INTO logs (amount) VALUES (?)', (amount,))
        conn.commit()
        conn.close()
    return jsonify({'status': 'success'})

# 集計データの取得（日別ブレイクダウン＋設定週の合計）
@app.route('/get_summary')
def get_summary():
    conn = get_db()
    c = conn.cursor()

    # 設定された週の開始日を取得
    c.execute('SELECT value FROM settings WHERE key = "week_start_date"')
    row = c.fetchone()
    start_str = row['value'] if row else datetime.now().strftime('%Y-%m-%d')
    week_start = datetime.strptime(start_str, '%Y-%m-%d')
    week_end = week_start + timedelta(days=7)

    # 今日の日付（YYYY-MM-DD）
    today_str = datetime.now().strftime('%Y-%m-%d')

    # 設定された7日間の日別集計
    daily_breakdown = []
    week_total = 0

    for i in range(7):
        day_start = week_start + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        
        c.execute('''SELECT SUM(amount) FROM logs 
                     WHERE created_at >= ? AND created_at < ?''',
                  (day_start.strftime('%Y-%m-%d 00:00:00'), day_end.strftime('%Y-%m-%d 00:00:00')))
        d_row = c.fetchone()
        d_total = d_row[0] if d_row[0] is not None else 0
        week_total += d_total

        day_str = day_start.strftime('%Y-%m-%d')
        daily_breakdown.append({
            'date_label': day_start.strftime('%m/%d'),
            'full_date': day_str,
            'total': d_total,
            'is_today': day_str == today_str
        })

    # 全期間の累計
    c.execute('SELECT SUM(amount) FROM logs')
    row_total = c.fetchone()
    total_all = row_total[0] if row_total[0] is not None else 0

    # 設定週の中での直近ログ5件
    c.execute('''SELECT id, amount, created_at 
                 FROM logs 
                 WHERE created_at >= ? AND created_at < ? 
                 ORDER BY id DESC LIMIT 5''',
              (week_start.strftime('%Y-%m-%d 00:00:00'), week_end.strftime('%Y-%m-%d 00:00:00')))
    logs = [{'id': r['id'], 'amount': r['amount'], 'time': r['created_at']} for r in c.fetchall()]

    conn.close()

    period_label = f"{week_start.strftime('%Y/%m/%d')}〜{(week_end - timedelta(days=1)).strftime('%m/%d')}"

    return jsonify({
        'week_start_date': start_str,
        'period_label': period_label,
        'week_total': week_total,
        'total_all': total_all,
        'daily_breakdown': daily_breakdown,
        'today_str': today_str,
        'recent_logs': logs
    })

# 直近ログ1件取消
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

# 個別削除
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

# 過去に設定された週ごとのアーカイブ一覧を取得
@app.route('/get_past_periods')
def get_past_periods():
    conn = get_db()
    c = conn.cursor()
    
    # 現在の設定週を取得
    c.execute('SELECT value FROM settings WHERE key = "week_start_date"')
    row = c.fetchone()
    current_start_str = row['value'] if row else datetime.now().strftime('%Y-%m-%d')
    current_start = datetime.strptime(current_start_str, '%Y-%m-%d')

    c.execute('SELECT amount, created_at FROM logs ORDER BY created_at ASC')
    rows = c.fetchall()
    conn.close()

    # 7日区切りでログを集計
    past_archives = {}
    for r in rows:
        try:
            dt = datetime.strptime(r['created_at'].split('.')[0], '%Y-%m-%d %H:%M:%S')
        except:
            dt = datetime.now()
            
        # 該当ログが含まれる7日間ブロック（現在設定週より前のもの）
        diff_days = (dt.date() - current_start.date()).days
        block_index = diff_days // 7
        
        block_start = current_start + timedelta(days=block_index * 7)
        block_end = block_start + timedelta(days=6)
        
        # 現在設定中の週以外をアーカイブとして記録
        if block_start < current_start:
            label = f"{block_start.strftime('%Y/%m/%d')}〜{block_end.strftime('%m/%d')}"
            past_archives[label] = past_archives.get(label, 0) + r['amount']

    result = [{'label': k, 'total': v} for k, v in reversed(list(past_archives.items()))]
    return jsonify({'archives': result})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
