from flask import render_template, request, url_for, redirect, flash
from flask_login import login_user, login_required, logout_user, current_user

from guabookseat import app, db
from guabookseat.models import User


@app.route('/', methods=['GET', 'POST'])
def index():  # put application's code here
    if request.method == 'POST':
        if not current_user.is_authenticated:
            return redirect(url_for('index'))

    return render_template('index.html')


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
        code = request.form['code']

        if not username or not password_1 or not password_2 or not code:
            flash('输入不能为空！')
            return redirect(url_for('logon'))

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


@app.route('/set-auto-booking')
@login_required
def set_auto_booking():
    # from guabookseat.test import test1
    # test1()
    return render_template('set-auto-booking.html')


@app.route('/set-config')
@login_required
def set_config():
    return render_template('set-config.html')


@app.route('/disable-auto-booking')
@login_required
def disable_auto_booking():
    # scheduler.remove(task_id)
    return 'auto-booking-disabled'
