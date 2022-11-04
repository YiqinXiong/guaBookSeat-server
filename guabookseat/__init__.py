import os.path
import re
import logging
from logging.handlers import TimedRotatingFileHandler
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from flask_apscheduler import APScheduler
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import MetaData

from guabookseat.settings import MyFlaskConfig
from guabookseat.seat_map import SeatMap

app = Flask(__name__)
# set app config
app.config.from_object(MyFlaskConfig())
# set logger
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'log')
os.makedirs(name=log_dir, exist_ok=True)
log_file_name = "LOG-guaBookSeat"
log_file_path = os.path.join(log_dir, log_file_name)
trh = TimedRotatingFileHandler(filename=log_file_path, encoding='utf-8', backupCount=7, when='MIDNIGHT', interval=1)
trh.suffix = "%Y-%m-%d.log"
trh.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}.log$")
trh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] (%(funcName)s) %(message)s"))
trh.setLevel(logging.INFO)
app.logger.addHandler(trh)
# set database
# 定义命名惯例
naming_convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}
db = SQLAlchemy(app=app, metadata=MetaData(naming_convention=naming_convention))
# set login_manager
login_manager = LoginManager(app)
# set flask-mail
mail = Mail(app)
# set apscheduler
scheduler = APScheduler(scheduler=BackgroundScheduler(), app=app)
scheduler.start()
# set migrate
migrate = Migrate(app=app, db=db, render_as_batch=True)
# load SeatMap
global_seat_map = SeatMap()


@login_manager.user_loader
def load_user(user_id):
    from guabookseat.models import User
    user = User.query.get(int(user_id))
    return user


login_manager.login_view = 'index'


# login_manager.login_message = 'Your custom message'


@app.context_processor
def inject_user():
    if current_user.is_authenticated:
        # 获取当前UserConfig（可能为None）
        from guabookseat.models import UserConfig
        current_config = UserConfig.query.filter_by(id=current_user.id).first()
        return dict(user=current_user, config=current_config)
    return dict(user={}, config={})


from guabookseat import views, errors, commands
