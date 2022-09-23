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

from guabookseat.settings import MyFlaskConfig

app = Flask(__name__)
# set app config
app.config.from_object(MyFlaskConfig())
# set logger
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'log')
os.makedirs(name=log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, "LOG-guaBookSeat")
trh = TimedRotatingFileHandler(filename=log_file_path, encoding='utf-8', backupCount=7, when='MIDNIGHT', interval=1)
trh.suffix = "%Y-%m-%d.log"
trh.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}.log$")
trh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] (%(funcName)s) %(message)s"))
trh.setLevel(logging.DEBUG)
app.logger.addHandler(trh)
# set database
db = SQLAlchemy(app)
# set login_manager
login_manager = LoginManager(app)
# set flask-mail
mail = Mail(app)
# set apscheduler
scheduler = APScheduler(scheduler=BackgroundScheduler(), app=app)
scheduler.start()


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
