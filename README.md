# guaBookSeat-server
A server-side deployment of guaBookSeat.

- Flask tutorial: [greyli/flask-tutorial](https://github.com/greyli/flask-tutorial/blob/master/chapters/SUMMARY.md)

## Deployment (Linux)
### Clone repository
```shell
git clone https://github.com/YiqinXiong/guaBookSeat-server.git
```
### Setup virtual environment of python
- Create venv
```shell
cd guaBookSeat-server
python3 -m venv env
```
- Activate venv
```shell
. env/bin/activate

# to deactivate venv
deactivate
```
- Install dependence
```shell
pip3 install wheel
pip3 install -r requirements.txt
```
### Initialize DB and create a superuser
```shell
# init sqlite3 and create a superuser('admin', 'foobar123')
flask create-admin --password foobar123
```
### Run server
```shell
# running server(0.0.0.0:16666) in the background using multithreading
nohup flask run -h 0.0.0.0 -p 16666 --no-debugger --with-threads > flask.log 2>&1 &
```
