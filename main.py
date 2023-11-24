import io
import zipfile
from flask import Flask, request, jsonify, render_template, redirect, send_from_directory, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

import requests
from bs4 import BeautifulSoup

import os
from dotenv import load_dotenv
import mysql.connector
import datetime
import uuid

from des_util import raw_str_enc
import hashlib

load_dotenv()

app = Flask(__name__, static_url_path='/', static_folder='static')
app.secret_key = os.getenv("secret.key")


@app.route('/upload/<path:filename>')
def download_file(filename):
    return send_from_directory("upload", filename)


# 连接数据库
db = mysql.connector.connect(
    host=os.getenv("db.host"),
    user=os.getenv("db.user"),
    password=os.getenv("db.password"),
    database=os.getenv("db.database")
)


class User(UserMixin):
    def __init__(self, id):
        self.id = id


login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    return redirect('/login')


@app.route('/')
def page_index():
    return render_template('index.html')


@app.route('/login')
def page_login():
    if current_user.is_authenticated:
        return redirect('/admin')
    return render_template('login.html')


@app.route('/admin')
@login_required
def page_admin():
    return render_template('admin.html')


@app.route('/api')
def api_index():
    return jsonify({'production': 'Shanghai Normal University 2023 Computer Science (Teacher Education) Class 2 '
                                  'All-in-one Service',
                    'author': 'Hong Yuxuan', 'environment': 'prod'})


@app.route('/api/user')
def api_user():
    cursor = db.cursor()
    query = "SELECT name FROM user WHERE uid=%s"
    cursor.execute(query, (f'{current_user.id}',))
    user = cursor.fetchone()
    return jsonify({'user': f'{user[0]}'})


# 登陆
@app.route('/api/login', methods=['POST'])
def api_login():
    session = requests.session()
    username = request.json.get('username')
    password = request.json.get('password')
    cursor = db.cursor()
    query = "SELECT * FROM user WHERE uid=%s AND isAdmin=1"
    cursor.execute(query, (username,))
    user = cursor.fetchone()
    if user is None:
        return jsonify({'msg': '非管理员'}), 401
    password_ = hashlib.sha1()
    password_.update(password.encode('utf-8'))
    password_enc = password_.hexdigest()
    # 优先比较数据库
    cursor = db.cursor()
    query = "SELECT * FROM user WHERE uid=%s AND password=%s"
    cursor.execute(query, (username, password_enc,))
    login = cursor.fetchone()
    if login:
        user = User(username)
        login_user(user)
        return jsonify({'msg': '登录成功'})
    # 接入校园网登录模块
    login_url = "https://cas.shnu.edu.cn/cas/login?service=http%3A%2F%2Fcourse.shnu.edu.cn%2Feams%2Flogin.action"
    response = session.get(login_url)
    if 'id="lt"' in response.text:
        soup = BeautifulSoup(response.text, "html.parser")
        lt_value = soup.find("input", {"id": "lt"})["value"]
    else:
        lt_value = ''
    if 'name="execution"' in response.text:
        execution = soup.find("input", {"name": "execution"})["value"]
    else:
        execution = "e1s1"
    data = {
        "rsa": raw_str_enc(username + password + lt_value),
        "ul": len(username),
        "pl": len(password),
        "lt": lt_value,
        "execution": execution,
        "_eventId": "submit",
    }
    post_headers = {
        "content-type": "application/x-www-form-urlencoded",
        "referer": login_url,
    }
    response = session.post(login_url, data=data, headers=post_headers)
    if "我的账户" not in response.text:
        return jsonify({'msg': '用户名或密码错误'}), 401
    cursor = db.cursor()
    query = "UPDATE user SET password=%s WHERE uid=%s"
    cursor.execute(query, (password_enc, username,))
    db.commit()
    user = User(username)
    login_user(user)
    return jsonify({'msg': '登录成功'})


# 添加签到任务
@app.route('/api/checkin/create', methods=['POST'])
@login_required
def api_checkin_create():
    task_name = request.json.get('taskName')
    expire_time = request.json.get('expireTime')
    uid = current_user.id
    # 参数校验
    expire_time_formatted = datetime.datetime.now() + datetime.timedelta(minutes=expire_time)
    formatted_date = expire_time_formatted.strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.cursor()
    cursor.execute("INSERT INTO checkin_task(taskName, expireTime, uid) VALUES(%s, %s, %s)",
                   (task_name, formatted_date, uid,))
    db.commit()
    return jsonify({'msg': '创建成功'})


# 签到
@app.route('/api/checkin/do', methods=['POST'])
def api_checkin_do():
    task_id = request.json.get('taskId')
    uid = request.json.get('uid')
    longitude = request.json.get("location")['lng']
    latitude = request.json.get("location")['lat']
    address = "位置：" + request.json.get("location")['address']
    if not longitude or not latitude:
        return jsonify({'msg': '无法获取位置信息！'}), 404
    if not uid or not task_id:
        return jsonify({'msg': '数据不完整！'}), 404
    do_cursor = db.cursor()
    query = "SELECT * FROM checkin_record WHERE uid=%s AND taskId=%s"
    do_cursor.execute(query, (uid, task_id,))
    user = do_cursor.fetchall()
    if user:
        return jsonify({'msg': '请勿重复签到！'}), 404
    time = datetime.datetime.now()
    in_cursor = db.cursor()
    in_cursor.execute("INSERT INTO checkin_record(taskId, uid, longitude, latitude, time, note) "
                      "VALUES(%s, %s, %s, %s, %s, %s)",
                      (task_id, uid, longitude, latitude, time, address,))
    db.commit()
    return jsonify({'msg': '签到成功'})


# 请假
@app.route('/api/checkin/leave', methods=['POST'])
@login_required
def api_checkin_leave():
    task_id = request.json.get('taskId')
    uid = request.json.get('uid')
    time = datetime.datetime.now()
    if not uid or not task_id:
        return jsonify({'msg': '数据不完整！'}), 404
    cursor = db.cursor()
    query = "SELECT name FROM user WHERE uid=%s"
    cursor.execute(query, (current_user.id,))
    task = cursor.fetchone()
    note = f"由{task[0]}请假"
    cursor.execute("INSERT INTO checkin_record(taskId, uid, time, note) VALUES(%s, %s, %s, %s)",
                   (task_id, uid, time, note,))
    db.commit()
    return jsonify({'msg': '请假成功'})


# 查看签到任务表
@app.route('/api/checkin/task', methods=['GET'])
def api_checkin_task():
    list_cursor = db.cursor()
    query = """SELECT t.taskId, t.taskName, t.expireTime, u.name  
         FROM checkin_task t 
         JOIN user u ON t.uid = u.uid"""
    list_cursor.execute(query, ())
    tasks = list_cursor.fetchall()
    if tasks is None:
        return jsonify({'msg': '无任务'}), 404
    if request.args.get('getValid'):
        valid_tasks = []
        for task in tasks:
            if task[2] >= datetime.datetime.now():
                valid_tasks.append(task)
        if valid_tasks is None:
            return jsonify({'msg': '无有效任务'}), 404
        column_names = [description[0] for description in list_cursor.description]
        data = {
            'items': [dict(zip(column_names, row)) for row in valid_tasks]
        }
        return jsonify(data)
    else:
        column_names = [description[0] for description in list_cursor.description]
        data = {
            'items': [dict(zip(column_names, row)) for row in tasks]
        }
        return jsonify(data)


# 查看未签到名单
@app.route('/api/checkin/list', methods=['GET'])
@login_required
def api_checkin_list():
    task_id = request.args.get('taskId')
    cursor = db.cursor()

    query = "SELECT * FROM checkin_task WHERE taskId=%s"
    cursor.execute(query, (task_id,))
    task = cursor.fetchone()
    if task is None:
        return jsonify({'msg': '任务不存在'}), 404

    query = """
    SELECT uid, name FROM user WHERE uid NOT IN (
      SELECT uid FROM checkin_record WHERE taskId=%s
    )
  """
    cursor.execute(query, (task_id,))
    unchecked = cursor.fetchall()
    column_names = [description[0] for description in cursor.description]
    data = {
        'items': [dict(zip(column_names, row)) for row in unchecked]
    }
    return jsonify(data)


# 查看签到记录
@app.route('/api/checkin/record', methods=['GET'])
@login_required
def api_checkin_record():
    task_id = request.args.get('taskId')
    cursor = db.cursor()

    query = "SELECT * FROM checkin_task WHERE taskId=%s"
    cursor.execute(query, (task_id,))
    task = cursor.fetchone()
    if task is None:
        return jsonify({'msg': '任务不存在'}), 404
    query = """SELECT r.uid, r.longitude, r.latitude, r.time, r.note, u.name
         FROM checkin_record r 
         JOIN user u ON r.uid = u.uid
         WHERE r.taskId=%s"""
    cursor.execute(query, (task_id,))
    records = cursor.fetchall()

    column_names = [description[0] for description in cursor.description]
    data = {
        'items': [dict(zip(column_names, row)) for row in records]
    }
    return jsonify(data)


# 添加收集任务
@app.route('/api/collect/create', methods=['POST'])
@login_required
def api_collect_create():
    task_name = request.json.get('taskName')
    expire_time = request.json.get('expireTime')
    task_type = request.json.get('taskType')
    if not task_type or not task_name or not expire_time:
        return jsonify({'msg': '参数不完整'}), 404
    uid = current_user.id
    cursor = db.cursor()
    cursor.execute("INSERT INTO collect_task(taskName, taskType, expireTime, uid) VALUES(%s, %s, %s, %s)",
                   (task_name, task_type, expire_time, uid,))
    db.commit()
    return jsonify({'msg': '创建成功'})


# 查看收集任务表
@app.route('/api/collect/task', methods=['GET'])
def api_collect_task():
    if not request.args.get('taskType'):
        return jsonify({'items': []})
    task_type = request.args.get('taskType')
    cursor = db.cursor()
    query = """SELECT t.taskId, t.taskName, t.expireTime, t.taskType, u.name  
         FROM collect_task t 
         JOIN user u ON t.uid = u.uid
         WHERE t.taskType=%s"""
    cursor.execute(query, (task_type,))
    tasks = cursor.fetchall()
    if tasks is None:
        return jsonify({'msg': '无任务'}), 404
    if request.args.get('getValid'):
        valid_tasks = []
        for task in tasks:
            if task[2] >= datetime.datetime.now():
                valid_tasks.append(task)
        if valid_tasks is None:
            return jsonify({'msg': '无有效任务'}), 404
        column_names = [description[0] for description in cursor.description]
        data = {
            'items': [dict(zip(column_names, row)) for row in valid_tasks]
        }
        return jsonify(data)
    else:
        column_names = [description[0] for description in cursor.description]
        data = {
            'items': [dict(zip(column_names, row)) for row in tasks]
        }
        return jsonify(data)


# 查看未提交名单
@app.route('/api/collect/list', methods=['GET'])
@login_required
def api_collect_list():
    task_id = request.args.get('taskId')
    cursor = db.cursor()

    query = "SELECT * FROM collect_task WHERE taskId=%s"
    cursor.execute(query, (task_id,))
    task = cursor.fetchone()
    if task is None:
        return jsonify({'msg': '任务不存在'}), 404

    query = """
    SELECT uid, name FROM user WHERE uid NOT IN (
      SELECT uid FROM collect_record WHERE taskId=%s
    )
  """
    cursor.execute(query, (task_id,))
    unchecked = cursor.fetchall()
    column_names = [description[0] for description in cursor.description]
    data = {
        'items': [dict(zip(column_names, row)) for row in unchecked]
    }
    return jsonify(data)


# 查看提交记录
@app.route('/api/collect/record', methods=['GET'])
@login_required
def api_collect_record():
    task_id = request.args.get('taskId')
    cursor = db.cursor()

    query = "SELECT * FROM collect_task WHERE taskId=%s"
    cursor.execute(query, (task_id,))
    task = cursor.fetchone()
    if task is None:
        return jsonify({'msg': '任务不存在'}), 404
    query = """SELECT r.uid, r.taskId, r.content, r.time, u.name
         FROM collect_record r 
         JOIN user u ON r.uid = u.uid
         WHERE r.taskId=%s"""
    cursor.execute(query, (task_id,))
    records = cursor.fetchall()

    column_names = [description[0] for description in cursor.description]
    data = {
        'items': [dict(zip(column_names, row)) for row in records]
    }
    return jsonify(data)


# 图片上传
@app.route('/api/upload', methods=['POST'])
def api_upload():
    image = request.files['file']
    filename = uuid.uuid4().hex + '.png'
    image.save(os.path.join('upload', filename))
    response = {
        "status": 0,
        "msg": "",
        "data": {
            "value": "upload/" + filename
        }
    }
    return jsonify(response)


# 收集提交
@app.route('/api/collect/do', methods=['POST'])
def api_collect_do():
    task_id = request.json.get('taskId')
    uid = request.json.get('uid')
    task_type = request.json.get('taskType')
    if not task_type or not task_id or not uid:
        return jsonify({'msg': '未知提交！'}), 404
    if task_type == "image":
        content = request.json.get('image')
    if task_type == "text":
        content = request.json.get('content')
    if not content:
        return jsonify({'msg': '非法提交！'}), 404
    cursor = db.cursor()
    query = "SELECT * FROM collect_record WHERE uid=%s AND taskId=%s"
    cursor.execute(query, (uid, task_id,))
    user = cursor.fetchall()
    if user:
        return jsonify({'msg': '请勿重复提交！'}), 404
    time = datetime.datetime.now()
    cursor = db.cursor()
    cursor.execute("INSERT INTO collect_record(taskId, uid, content, time) "
                   "VALUES(%s, %s, %s, %s)",
                   (task_id, uid, content, time,))
    db.commit()
    return jsonify({'msg': '提交成功'})


# 图片收集打包下载
@app.route('/api/collect/download', methods=['GET'])
@login_required
def api_collect_download():
    task_id = request.args.get('taskId')
    cursor = db.cursor()
    query = "SELECT taskName FROM collect_task WHERE taskId=%s"
    cursor.execute(query, (task_id,))
    task = cursor.fetchone()
    if task is None:
        return jsonify({'msg': '任务不存在'}), 404
    query = """SELECT r.content, u.name  
               FROM collect_record r
               JOIN user u ON r.uid = u.uid
               WHERE r.taskId=%s"""
    cursor.execute(query, (task_id,))
    records = cursor.fetchall()
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        for r in records:
            path, name = r
            filename = f'{name}-{path.split("/")[-1]}'  # 构造文件名
            zf.write(path, filename)
    memory_file.seek(0)
    return send_file(memory_file, download_name=f'{task[0]}收集结果.zip',
                     as_attachment=True)


# 抽签用户组
@app.route('/api/lottery/list', methods=['GET'])
@login_required
def api_lottery_list():
    cursor = db.cursor()
    query = "SELECT DISTINCT role FROM user_role"
    cursor.execute(query, ())
    roles = cursor.fetchall()
    if roles is None:
        return jsonify({'msg': '用户组不存在'}), 404
    data = {
        'status': 0,
        'msg': '',
        'data': {
            'options': []
        }
    }
    data['data']['options'].append({
        'label': '全体',
        'value': '全体'
    })
    for role in roles:
        data['data']['options'].append({
            'label': role[0],
            'value': role[0]
        })
    return jsonify(data)


# 抽签
@app.route('/api/lottery/do', methods=['POST'])
@login_required
def api_lottery_do():
    cursor = db.cursor()
    role = request.json.get('select')
    num = request.json.get('num')
    if num is None:
        num = 1
    if role == '全体':
        query = """SELECT name FROM user ORDER BY RAND() LIMIT %s"""
        cursor.execute(query, (num,))
    else:
        query = """SELECT u.name
             FROM user_role r
             JOIN user u ON r.uid = u.uid
             WHERE role=%s ORDER BY RAND() LIMIT %s"""
        cursor.execute(query, (role, num,))
    user = cursor.fetchall()
    if user is None:
        return jsonify({'msg': '用户不存在'}), 404
    return jsonify({'name': user})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
