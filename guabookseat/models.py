from flask_login import UserMixin
from sqlalchemy import ForeignKey
from werkzeug.security import generate_password_hash, check_password_hash

from guabookseat import db


class User(db.Model, UserMixin):  # 表名将会是 user（自动生成，小写处理）
    id = db.Column(db.Integer, primary_key=True)  # 主键
    username = db.Column(db.String(20))
    password_hash = db.Column(db.String(128))

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

    def set_config(self, config_data):
        self.id = config_data['id']
        self.student_id = config_data['student_id']
        self.student_pwd = config_data['student_pwd']
        self.content_id = config_data['content_id']
        self.start_time = config_data['start_time']
        self.duration = config_data['duration']
        self.start_time_delta_limit = config_data['start_time_delta_limit']
        self.duration_delta_limit = config_data['duration_delta_limit']
        self.target_seat = config_data['target_seat']
