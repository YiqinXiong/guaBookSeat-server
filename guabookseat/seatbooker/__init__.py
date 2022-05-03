import logging
import os
import re
import sys
from logging.handlers import TimedRotatingFileHandler

from .my_tool import parent_dir_name, load_json_conf, get_start_time, get_start_end_timestr

# logging初始化配置
sh = logging.StreamHandler(sys.stdout)
trh = TimedRotatingFileHandler(os.path.join(parent_dir_name, "LOG-guaBookSeat"), encoding='utf-8', backupCount=3,
                               when='MIDNIGHT', interval=1)
trh.suffix = "%Y-%m-%d.log"
trh.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}.log$")
fmt = "[%(asctime)s] [%(levelname)s] (%(funcName)s line:%(lineno)s) %(message)s"
logging.basicConfig(level=logging.INFO, handlers=[sh, trh], format=fmt, datefmt="%Y-%m-%d %H:%M:%S")

from guabookseat.seatbooker import my_tool, seat_booker
