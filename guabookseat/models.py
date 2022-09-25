import json
import time

from flask_login import UserMixin
from sqlalchemy import ForeignKey
from werkzeug.security import generate_password_hash, check_password_hash

from guabookseat import db


class User(db.Model, UserMixin):  # 表名将会是 user（自动生成，小写处理）
    id = db.Column(db.Integer, primary_key=True)  # 主键
    username = db.Column(db.String(20), unique=True)
    password_hash = db.Column(db.String(128))
    mail_address = db.Column(db.String(40))

    def set_password(self, password):
        # 生成密码哈希值
        self.password_hash = generate_password_hash(password)

    def validate_password(self, password):
        # 验证哈希后的密码
        return check_password_hash(self.password_hash, password)


class UserConfig(db.Model):
    cid = db.Column(db.Integer, primary_key=True)
    id = db.Column(db.Integer, ForeignKey('user.id'), unique=True)  # 外键
    student_id = db.Column(db.String(20))  # 学号
    student_pwd = db.Column(db.String(20))  # 密码
    content_id = db.Column(db.Integer)  # 房间号
    start_time = db.Column(db.Integer)  # 开始时间（点）
    duration = db.Column(db.Integer)  # 持续时间（小时）
    start_time_delta_limit = db.Column(db.Integer)  # 开始时间容许误差（小时）
    duration_delta_limit = db.Column(db.Integer)  # 持续时间容许误差（小时）
    target_seat = db.Column(db.Integer)  # 目标座位号

    def set_config(self, config_data, cur_user_id):
        self.id = cur_user_id
        self.student_id = config_data['student_id']
        self.student_pwd = config_data['student_pwd']
        self.content_id = int(config_data['content_id'])
        self.start_time = int(config_data['start_time'])
        self.duration = int(config_data['duration'])
        self.start_time_delta_limit = int(config_data['start_time_delta_limit'])
        self.duration_delta_limit = int(config_data['duration_delta_limit'])
        self.target_seat = int(config_data['target_seat'])

    def get_config(self):
        config_map = {
            'username': self.student_id,
            'password': self.student_pwd,
            'content_id': self.content_id,
            'start_time': self.start_time,
            'duration': self.duration,
            'seat_id': self.target_seat,
            'category_id': 591,
            'start_time_delta': self.start_time_delta_limit,
            'duration_delta': self.duration_delta_limit,
        }
        return config_map


class UserCookie(db.Model):
    cid = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True)  # 自习室账号
    uid = db.Column(db.Integer, unique=True)  # 网页uid
    cookie = db.Column(db.String(512))  # cookie json 字符串
    expire_time = db.Column(db.Integer)  # 过期时间戳

    def set_cookie(self, cookie, username, uid):
        self.username = username
        self.uid = uid
        self.cookie = json.dumps(cookie)
        self.expire_time = int(time.time()) + 3 * 24 * 3600  # cookie 3天后过期

    def is_expired(self):
        return time.time() > self.expire_time

    def get_cookie(self):
        return json.loads(self.cookie)

    def get_uid(self):
        return self.uid
