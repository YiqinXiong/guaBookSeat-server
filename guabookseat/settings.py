import os, shutil

import json
import logging
import tzlocal
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from datetime import timedelta

def get_config_from_file():
    my_config_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    try:
        with open(my_config_file) as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        logging.warning(f"Config file `config.json` not found, copy from template file")
        my_config_template_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template-config.json")
        try:
            shutil.copy(my_config_template_file, my_config_file)
        except IOError as e:
            logging.critical(f"copy from {my_config_template_file} failed")
            return None
        return get_config_from_file()


class MyFlaskConfig(object):
    # --------读取json配置--------
    config = get_config_from_file()
    # --------session过期时间--------
    json_session_life_time = config['session_life_time'] if 'session_life_time' in config else 600
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=json_session_life_time)
    # --------环境变量--------
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev')
    # --------访问DB--------
    # DB路径
    prefix = "sqlite:///"
    SQLALCHEMY_DATABASE_URI = prefix + os.path.join(os.path.dirname(__file__), 'data.db')
    # 模型修改的监控开关
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # --------任务调度APScheduler--------
    json_scheduler = config['scheduler']  if 'scheduler' in config else {}
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
            'max_workers': json_scheduler['max_workers'] if 'max_workers' in json_scheduler else 32
        }
    }
    # job默认设置
    SCHEDULER_JOB_DEFAULTS = {
        'coalesce': True,
        'max_instances': json_scheduler['max_instances'] if 'max_instances' in json_scheduler else 32,
        'misfire_grace_time': json_scheduler['misfire_grace_time'] if 'misfire_grace_time' in json_scheduler else 600
    }
    # 时区
    SCHEDULER_TIMEZONE = str(tzlocal.get_localzone())
    # --------邮箱Flask-Mail--------
    json_mail = config['mail']  if 'mail' in config else {}
    MAIL_SERVER = json_mail['server'] if 'server' in json_mail else "smtp.qq.com"
    MAIL_PORT = json_mail['port'] if 'port' in json_mail else 465
    MAIL_USE_SSL = json_mail['use_ssl'] if 'use_ssl' in json_mail else True
    MAIL_USE_TLS = json_mail['use_tls'] if 'use_tls' in json_mail else False
    MAIL_USERNAME = json_mail['username'] if 'username' in json_mail else "foobar@qq.com"
    MAIL_PASSWORD = json_mail['password'] if 'password' in json_mail else "foobarfoobar"
    MAIL_DEFAULT_SENDER = json_mail['default_sender'] if 'default_sender' in json_mail else "foobar@qq.com"
