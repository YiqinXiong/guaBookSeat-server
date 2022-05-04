import os

import tzlocal
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore


class MyFlaskConfig(object):
    # --------环境变量--------
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev')
    # --------访问DB--------
    # DB路径
    prefix = "sqlite:///"
    SQLALCHEMY_DATABASE_URI = prefix + os.path.join(os.path.dirname(__file__), 'data.db')
    # 模型修改的监控开关
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # --------任务调度APScheduler--------
    # 调度器开关
    SCHEDULER_API_ENABLED = True
    # job持久化
    SCHEDULER_JOBSTORES = {
        'default': SQLAlchemyJobStore(url=prefix + os.path.join(os.path.dirname(__file__), 'booking_tasks.db'))
    }
    # 线程池配置
    SCHEDULER_EXECUTORS = {
        'default': {
            'type': 'threadpool',
            'max_workers': 64
        }
    }
    # job默认设置
    SCHEDULER_JOB_DEFAULTS = {
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 120
    }
    # 时区
    SCHEDULER_TIMEZONE = str(tzlocal.get_localzone())
    # --------邮箱Flask-Mail--------
    MAIL_SERVER = "smtp.qq.com"
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USE_TLS = False
    MAIL_USERNAME = "foobar@qq.com"
    MAIL_PASSWORD = "foobarfoobar"
    MAIL_DEFAULT_SENDER = "foobar@qq.com"

