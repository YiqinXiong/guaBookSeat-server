import click
import markdown

from guabookseat import app, db, mail
from guabookseat.models import User, UserConfig
from flask_mail import Message


@app.cli.command()
@click.option('--drop', is_flag=True, help='Create after drop.')
def initdb(drop):
    """Initialize the database."""
    if drop:
        db.drop_all()
    db.create_all()
    click.echo('Initialized database.')


@app.cli.command()
def forge():
    """Generate fake data."""
    db.create_all()

    username = 'foofoo'
    password = 'barbar'

    configs = [
        {
            'id': 1,
            'student_id': '201826801092',
            'student_pwd': 'foo',
            'content_id': '31',
            'start_time': 9,
            'duration': 13,
            'start_time_delta_limit': 0,
            'duration_delta_limit': 1,
            'target_seat': 259,
        },
        {
            'id': 2,
            'student_id': '201926804010',
            'student_pwd': 'bar',
            'content_id': '31',
            'start_time': 8,
            'duration': 10,
            'start_time_delta_limit': 0,
            'duration_delta_limit': 1,
            'target_seat': 255,
        }
    ]

    user = User()
    user.username = username
    user.set_password(password)
    db.session.add(user)
    for c in configs:
        conf = UserConfig()
        conf.set_config(c, c['id'])
        db.session.add(conf)
    db.session.commit()
    click.echo('Done.')


@app.cli.command()
# @click.option('--username', prompt=True, help='The username used to login.')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='The password used to login.')
def create_admin(password):
    """Create user."""
    db.create_all()
    user = User.query.filter_by(username='admin').first()
    if user is not None:
        click.echo('Updating user...')
        user.username = 'admin'
        user.set_password(password)
    else:
        click.echo('Creating user...')
        user = User()
        user.username = 'admin'
        user.set_password(password)
        db.session.add(user)
    db.session.commit()
    click.echo('Done.')


@app.cli.command()
@click.option('--title', prompt=True, help='mail title')
@click.option('--file', prompt=True, help='mail text file path')
@click.option('--test', is_flag=True, help='If test or not')
def notify_update(title, file, test):
    try:
        with open(file) as f:
            body = f.read()
            html_body = markdown.markdown(body)
    except FileNotFoundError:
        app.logger.critical(f"mail text file {file} not found")

    receivers = set()
    if test:
        admin_user = User.query.filter_by(username='admin').first()
        if admin_user.mail_address:
            receivers.add(admin_user.mail_address)
    else:
        users = User.query.all()
        for user in users:
            if user.mail_address:
                receivers.add(user.mail_address)

    msg = Message(subject=title, recipients=list(receivers), html=html_body, sender=app.config['MAIL_DEFAULT_SENDER'])
    try:
        with app.app_context():
            mail.send(msg)
    except Exception as e:
        app.logger.error(f"send_email raise an Exception:\n{e}")
