from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from flask_apscheduler import APScheduler
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy

from guabookseat.settings import MyFlaskConfig

app = Flask(__name__)
app.config.from_object(MyFlaskConfig())
db = SQLAlchemy(app)
login_manager = LoginManager(app)
mail = Mail(app)
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
