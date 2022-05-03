from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from flask_apscheduler import APScheduler
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy

from guabookseat.settings import MyFlaskConfig

app = Flask(__name__)
app.config.from_object(MyFlaskConfig())
db = SQLAlchemy(app)
login_manager = LoginManager(app)
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
        from guabookseat.models import UserConfig
        current_config = UserConfig.query.filter_by(id=current_user.id).first()
        histories = [
            {
                'loc': '南二自习室（201）',
                'seat': '#259',
                'time': '2022年5月2日 17:52至22:00',
                'status': '已签退结束'
            },
            {
                'loc': '南二自习室（201）',
                'seat': '#231',
                'time': '2022年5月1日 8:00至22:00',
                'status': '未签退结束'
            }
        ]
        auto_booking_info = {
            'enable': False,
            'task_id': "auto_booking_<username>",
            'next_order_time': "2022年5月2日 22:01:10"
        }
        return dict(user=current_user, config=current_config, histories=histories, auto_booking_info=auto_booking_info)
    return dict(user={}, config={}, histories={}, auto_booking_info={})


from guabookseat import views, errors, commands
