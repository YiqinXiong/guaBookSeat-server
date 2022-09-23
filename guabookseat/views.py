import threading

from flask import render_template, request, url_for, redirect, flash
from flask_login import login_user, login_required, logout_user, current_user

from guabookseat import app, db, scheduler
from guabookseat.constants import Constants
from guabookseat.models import User, UserConfig
from guabookseat.scheduled_jobs import call_seat_booker_func, auto_booking


@app.route('/', methods=['GET', 'POST'])
def index():  # put application's code here
    auto_booking_info = None
    if current_user.is_authenticated:
        # 获取当前job（可能为None）
        job_id = 'daily_auto_booking_' + str(current_user.id)
        booking_job = scheduler.get_job(id=job_id)
        # 当前自动预约信息
        auto_booking_info = {
            'enable': booking_job is not None,
            'task_id': job_id,
            'next_order_time': booking_job.next_run_time.strftime('%Y年%m月%d日 %H:%M:%S') if booking_job else None
        }
    if request.method == 'POST':
        if not current_user.is_authenticated:
            return redirect(url_for('index'))

    return render_template('index.html', valid_rooms=Constants.valid_rooms, auto_booking_info=auto_booking_info)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            flash('输入不能为空！')
            return redirect(url_for('index'))

        user = User.query.filter_by(username=username).first()

        if not user:
            flash("用户不存在！")
        elif user.validate_password(password):
            login_user(user)
            flash('登录成功！')
        else:
            flash('密码错误！')

    return redirect(url_for('index'))


@app.route('/logon', methods=['GET', 'POST'])
def logon():
    if request.method == 'POST':
        username = request.form['username']
        password_1 = request.form['password_1']
        password_2 = request.form['password_2']
        mail_address = request.form['mail_address']
        code = request.form['code']

        if User.query.filter_by(username=username).first():
            flash('用户名已被注册！')
            return redirect(url_for('logon'))

        if code != "xyqlth":
            flash('邀请码无效！')
            return redirect(url_for('logon'))

        if password_1 != password_2:
            flash('两次密码不一致！')
            return redirect(url_for('logon'))

        user = User()
        user.username = username
        user.set_password(password_1)
        user.mail_address = mail_address if mail_address != "" else None
        db.session.add(user)
        db.session.commit()
        flash('注册成功！')
        return redirect(url_for('index'))

    return render_template('logon.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录！')
    return redirect(url_for('index'))


@app.route('/set-auto-booking', methods=['GET', 'POST'])
@login_required
def set_auto_booking():
    if request.method == 'POST':
        flash_str = ""
        # 更新邮箱
        mail_address = request.form['mail_address'] if request.form['mail_address'] != "" else None
        if mail_address != current_user.mail_address:
            user = User.query.get(current_user.id)
            user.mail_address = mail_address
            db.session.commit()
            flash_str += "邮箱已更新！"
        # 更新自动预约任务时间
        cur_config_id = int(request.form['config_id'])
        order_time = request.form['order_time'].split(':')
        userconfig = UserConfig.query.get(cur_config_id)
        job_id = 'daily_auto_booking_' + str(current_user.id)
        if scheduler.get_job(id=job_id):
            scheduler.remove_job(id=job_id)
        scheduler.add_job(id=job_id, func=auto_booking, trigger='cron', hour=order_time[0], minute=order_time[1],
                          args=[userconfig.get_config(), mail_address])
        flash_str += "自动预约任务时间已更新！"
        flash(flash_str)
        return redirect(url_for('index'))

    return render_template('set-auto-booking.html')


@app.route('/set-config', methods=['GET', 'POST'])
@login_required
def set_config():
    if request.method == 'POST':
        # print(request.form)
        cur_config_id = int(request.form['config_id'])
        if cur_config_id == 0:
            userconfig = UserConfig()
            userconfig.set_config(config_data=request.form, cur_user_id=current_user.id)
            db.session.add(userconfig)
            db.session.commit()
            flash('添加订座信息成功！')
            return redirect(url_for('index'))
        else:
            userconfig = UserConfig.query.get(cur_config_id)
            userconfig.set_config(config_data=request.form, cur_user_id=current_user.id)
            db.session.commit()
            job_id = 'daily_auto_booking_' + str(current_user.id)
            if scheduler.get_job(id=job_id):
                scheduler.modify_job(id=job_id, args=[userconfig.get_config(), current_user.mail_address])
            flash('修改订座信息成功！')
            return redirect(url_for('index'))

    return render_template('set-config.html', valid_rooms=Constants.valid_rooms,
                           valid_start_times=Constants.valid_start_times,
                           valid_durations=Constants.valid_durations,
                           valid_start_time_delta_limits=Constants.valid_start_time_delta_limits,
                           valid_duration_delta_limits=Constants.valid_duration_delta_limits)


@app.route('/disable-auto-booking')
@login_required
def disable_auto_booking():
    job_id = 'daily_auto_booking_' + str(current_user.id)
    if scheduler.get_job(id=job_id):
        scheduler.remove_job(id=job_id)
    return redirect(url_for('index'))


@app.route('/show-booking-list')
@login_required
def show_booking_list():
    histories = None
    if current_user.is_authenticated:
        # 获取当前histories（可能为None）
        current_config = UserConfig.query.filter_by(id=current_user.id).first()
        histories = call_seat_booker_func(conf=current_config.get_config(),
                                          func_name='get_histories') if current_config else None
    return render_template('show-booking-list.html', histories=histories)


@app.route('/manual-booking')
@login_required
def manual_booking():
    userconfig = UserConfig.query.filter_by(id=current_user.id).first()
    new_thread = threading.Thread(target=auto_booking, args=(userconfig.get_config(), current_user.mail_address))
    new_thread.start()
    flash("手动预约任务正在后台运行！")
    return redirect(url_for('index'))
