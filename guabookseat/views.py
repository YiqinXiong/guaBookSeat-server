import json
import os
import sqlite3
import threading
import time

from flask import render_template, request, url_for, redirect, flash
from flask_login import login_user, login_required, logout_user, current_user

from guabookseat import app, db, scheduler, log_dir, log_file_name
from guabookseat.constants import Constants
from guabookseat.models import User, UserConfig
from guabookseat.scheduled_jobs import call_seat_booker_func, auto_booking
from guabookseat.seatbooker.seat_booker import SeatBookerStatus


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
            'paused': booking_job.next_run_time is None if booking_job else True,
            'task_id': job_id,
            'next_order_time': booking_job.next_run_time.strftime(
                '%Y年%m月%d日 %H:%M') if booking_job and booking_job.next_run_time else "无计划"
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
            app.logger.info(f"USER:{username} PASSWORD:{password} LOGIN guabookSeat SUCCESS!")
        else:
            flash('密码错误！')
            app.logger.info(f"USER:{username} PASSWORD:{password} LOGIN guabookSeat FAILED!")

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
        # 更新邮箱
        mail_address = request.form['mail_address'] if request.form['mail_address'] != "" else None
        mail_changed = mail_address != current_user.mail_address
        if mail_changed:
            user = User.query.get(current_user.id)
            user.mail_address = mail_address
            db.session.commit()
        # 更新自动预约任务时间
        order_time = request.form['order_time'].split(':')
        job_id = 'daily_auto_booking_' + str(current_user.id)
        cur_job = scheduler.get_job(id=job_id)
        cur_config_id = int(request.form['config_id'])
        userconfig = UserConfig.query.get(cur_config_id)
        # 存在任务则修改
        if cur_job:
            cur_time = cur_job.next_run_time
            time_changed = int(order_time[0]) != cur_time.hour or int(
                order_time[1]) != cur_time.minute if cur_time else True
            job_paused = cur_time is None
            # 分情况修改任务
            if mail_changed and time_changed:
                scheduler.modify_job(id=job_id, trigger='cron', hour=order_time[0], minute=order_time[1],
                                     args=[userconfig.get_config(), mail_address])
            elif mail_changed:
                scheduler.modify_job(id=job_id, args=[userconfig.get_config(), mail_address])
            elif time_changed:
                scheduler.modify_job(id=job_id, trigger='cron', hour=order_time[0], minute=order_time[1])
            else:
                pass
            # 若之前任务为暂停状态，继续暂停任务
            if job_paused:
                scheduler.pause_job(id=job_id)
        # 不存在任务则添加
        else:
            scheduler.add_job(id=job_id, func=auto_booking, trigger='cron', hour=order_time[0], minute=order_time[1],
                              args=[userconfig.get_config(), mail_address])
            time_changed = True
        # 提示信息
        if mail_changed or time_changed:
            flash_str = "邮箱已更新！" if mail_changed else ""
            flash_str += "自动预约任务时间已更新！" if time_changed else ""
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
                           max_end_time=Constants.MAX_END_TIME,
                           valid_start_time_delta_limits=Constants.valid_start_time_delta_limits,
                           valid_duration_delta_limits=Constants.valid_duration_delta_limits)


@app.route('/get-valid-durations', methods=['GET', 'POST'])
@login_required
def get_valid_durations():
    if request.method == 'POST':
        data = request.get_json()
        start_time = int(data['start_time'])
        cur_max_end_time = Constants.MAX_END_TIME - start_time
        valid_durations = [x for x in range(3, cur_max_end_time + 1)]
        return json.dumps(valid_durations)


@app.route('/pause-auto-booking')
@login_required
def pause_auto_booking():
    job_id = 'daily_auto_booking_' + str(current_user.id)
    if scheduler.get_job(id=job_id):
        scheduler.pause_job(id=job_id)
    return redirect(url_for('index'))


@app.route('/resume-auto-booking')
@login_required
def resume_auto_booking():
    job_id = 'daily_auto_booking_' + str(current_user.id)
    if scheduler.get_job(id=job_id):
        scheduler.resume_job(id=job_id)
    return redirect(url_for('index'))


@app.route('/show-booking-list')
@login_required
def show_booking_list():
    histories = None
    if current_user.is_authenticated:
        # 获取当前histories（可能为None）
        current_config = UserConfig.query.filter_by(id=current_user.id).first()
        try:
            histories = call_seat_booker_func(conf=current_config.get_config(),
                                              func_name='get_histories') if current_config else None
        except RuntimeError as e:
            flash(str(e))
        else:
            if histories:
                histories = [list(his) for his in histories]
                # 筛选出需要手动签到的项
                for his in histories:
                    if his[0] == '已预约，等待签到':
                        booking_id = his[5]
                        job_id = 'checkin_booking_' + str(booking_id)
                        if scheduler.get_job(id=job_id):
                            his[0] = '已预约，已创建定时签到任务'

    return render_template('show-booking-list.html', histories=histories)


@app.route('/manual-booking')
@login_required
def manual_booking():
    userconfig = UserConfig.query.filter_by(id=current_user.id).first()
    new_thread = threading.Thread(target=auto_booking, args=(userconfig.get_config(), current_user.mail_address))
    new_thread.start()
    flash("手动预约任务正在后台运行！")
    return redirect(url_for('index'))


@app.route('/manual-checkin')
@login_required
def manual_checkin():
    if request.method == "GET":
        booking_id = int(request.args.get('booking_id'))
        begin_time_stamp = request.args.get('begin_time')
        checkin_time_stamp = int(begin_time_stamp) - 60 * 10  # 提前10分钟

        userconfig = UserConfig.query.filter_by(id=current_user.id).first()
        conf = userconfig.get_config()
        receiver = current_user.mail_address

        if checkin_time_stamp <= time.time():
            # 立即签到
            try:
                stat = call_seat_booker_func(conf=conf, func_name='checkin_booking_immediately',
                                             receiver=receiver, booking_id=booking_id)
            except RuntimeError as e:
                flash(str(e))
            else:
                if stat == SeatBookerStatus.SUCCESS:
                    flash("签到成功！")
                elif stat == SeatBookerStatus.NO_NEED:
                    flash("无需签到！")
                else:
                    flash("签到失败，请重试！")
        else:
            # 创建定时签到任务
            job_id = 'checkin_booking_' + str(booking_id)
            checkin_time = time.localtime(checkin_time_stamp)
            if not scheduler.get_job(id=job_id):
                scheduler.add_job(id=job_id, func=call_seat_booker_func, trigger='date',
                                  run_date=time.strftime("%Y-%m-%d %H:%M:%S", checkin_time),
                                  args=[conf, 'checkin_booking', receiver, booking_id])
            app.logger.info(f"UID:{conf['username']} CREATE AUTO_CHECKIN_JOB SUCCESS!")
            flash("未到签到时段，已创建定时签到任务，到时会自动签到")

    return redirect(url_for('show_booking_list'))


@app.route('/show-log')
@login_required
def show_log():
    date_logs = []
    flask_log = None
    # 遍历日志文件夹
    date_log_dir = log_dir
    date_log_prefix = log_file_name
    for date_log_name in os.listdir(date_log_dir):
        if date_log_name.startswith(date_log_prefix):
            suffix = date_log_name.split(date_log_prefix)[1]  # 后缀，比如 ".2022-09-28.log"
            date = suffix.split('.')[1] if suffix else "最新日志"
            try:
                with open(os.path.join(date_log_dir, date_log_name), 'r') as f:
                    log_content = f.read()
            except UnicodeDecodeError:
                with open(os.path.join(date_log_dir, date_log_name), 'r', encoding='gbk') as f:
                    log_content = f.read()
            date_logs.append((date, log_content))
    date_logs.sort(reverse=True)  # 排序
    # 打开Flask日志文件
    flask_log_dir = os.path.dirname(date_log_dir)
    flask_log_name = "flask.log"
    try:
        with open(os.path.join(flask_log_dir, flask_log_name), 'r') as f:
            flask_log = "".join(f.readlines()[-200:])
    except FileNotFoundError:
        pass
    except UnicodeDecodeError:
        with open(os.path.join(flask_log_dir, flask_log_name), 'r', encoding='utf-16') as f:
            flask_log = "".join(f.readlines()[-200:])

    return render_template('show-log.html', date_logs=date_logs, flask_log=flask_log)


@app.route('/show-tables')
@login_required
def show_tables():
    user_content = User.query.all()
    user_head = [('用户ID', '用户名', '邮箱')]
    user_content = user_head + [(x.id, x.username, x.mail_address) for x in user_content]

    user_config_content = UserConfig.query.all()
    user_config_head = [('设置ID', '用户ID', '学号', '密码', '自习室', '开始', '持续', '开始offset', '持续offset', '座位')]
    user_config_content = user_config_head + [
        (x.cid, x.id, x.student_id, x.student_pwd, Constants.valid_rooms[x.content_id], x.start_time,
         x.duration, x.start_time_delta_limit, x.duration_delta_limit, x.target_seat) for x in
        user_config_content]

    task_db_path = os.path.join(os.path.dirname(__file__), 'booking_tasks.db')
    conn = sqlite3.connect(task_db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, next_run_time from apscheduler_jobs")
    apscheduler_jobs_content = cursor.fetchall()
    cursor.close()
    conn.close()
    apscheduler_jobs_head = [('任务ID', '下次运行时间')]
    apscheduler_jobs_content = apscheduler_jobs_head + apscheduler_jobs_content

    tables = {
        '用户信息': user_content,
        '用户设置信息': user_config_content,
        '定时任务信息': apscheduler_jobs_content,
    }

    return render_template('show-tables.html', tables=tables)
