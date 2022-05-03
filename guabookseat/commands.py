import click

from guabookseat import app, db
from guabookseat.models import User, UserConfig


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

    username = 'xyq6785665'
    password = 'xyq1999411'

    configs = [
        {
            'id': 1,
            'student_id': '201826801092',
            'student_pwd': '666666',
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
            'student_pwd': 'xiongru010308',
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
        conf.set_config(c)
        db.session.add(conf)
    db.session.commit()
    click.echo('Done.')


@app.cli.command()
# @click.option('--username', prompt=True, help='The username used to login.')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='The password used to login.')
def create_admin(password):
    """Create user."""
    # db.create_all()
    user = User.query.first()
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
