import logging
import os
import sys
import time
from enum import Enum
from random import randint

import requests

from my_tool import parent_dir_name, get_start_time, get_start_end_timestr


# SeatBooker状态枚举类
class SeatBookerStatus(Enum):
    SUCCESS = 1
    NO_SEAT = 2
    NOT_AFFORDABLE = 3
    STATUS_CODE_ERROR = 4
    TIME_OUT = 5
    PARAM_ERROR = 6
    UNKNOWN_ERROR = 7
    ALREADY_BOOKED = 8
    LOOP_FAILED = 9
    LOGIN_FAILED = 10
    PROXY_ERROR = 11


def create_auto_cancel_task(start_timestamp):
    # 创建一个自动取消预订的任务
    auto_cancel_script_path = os.path.join(parent_dir_name, "src", "auto_cancel.py")
    ddl_t = time.localtime(start_timestamp + 60 * 25)  # 开始时间25分钟后如果还没签到就自动取消
    cancel_time = time.strftime("%H:%M", ddl_t)
    cancel_date = time.strftime("%Y/%m/%d", ddl_t)
    if os.name == 'nt':
        create_auto_cancel_task_cmd = 'SCHTASKS /CREATE /TN "cancel_booking" '
        create_auto_cancel_task_cmd += f'/TR "cmd /c python3 {auto_cancel_script_path}" '
        create_auto_cancel_task_cmd += f'/SC ONCE /ST {cancel_time} /SD {cancel_date} /F'
    else:
        cancel_cron_time = time.strftime("%M %H %d %m *")
        create_auto_cancel_task_cmd = f'echo "{cancel_cron_time} {sys.executable} {auto_cancel_script_path}" > {parent_dir_name}/auto_cancel.cfg '
        create_auto_cancel_task_cmd += f'&& crontab {parent_dir_name}/auto_cancel.cfg '
        create_auto_cancel_task_cmd += f'&& rm {parent_dir_name}/auto_cancel.cfg'
    os.system(create_auto_cancel_task_cmd)


# SeatBooker类
class SeatBooker:
    def __init__(self, conf) -> None:
        # 读取参数配置
        self.uid = None
        self.username = conf['username']
        self.password = conf['password']
        self.content_id = conf['content_id']
        self.start_time = get_start_time(conf['start_time'])
        self.duration = 3600 * conf['duration']
        self.seat_id = conf['seat_id']
        self.category_id = conf['category_id']
        self.start_time_delta_limit = 3600 * conf['start_time_delta']
        self.duration_delta_limit = 3600 * conf['duration_delta']
        # 成员变量
        self.target_seat = ""
        self.target_seat_title = ""
        self.start_time_delta = 0
        self.duration_delta = 0
        # 建链相关
        fake_header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/100.0.4896.60 Safari/537.36',
            'Referer': 'https://jxnu.huitu.zhishulib.com/'
        }
        url_home = 'https://jxnu.huitu.zhishulib.com'
        self.urls = {
            'login': url_home + '/api/1/login',
            'search_seat': url_home + '/Seat/Index/searchSeats?LAB_JSON=1',
            'book_seat': url_home + '/Seat/Index/bookSeats?LAB_JSON=1',
            'get_my_booking_list': url_home + '/Seat/Index/myBookingList?LAB_JSON=1'
        }
        self.session = requests.session()
        self.session.headers.update(fake_header)

    def is_time_affordable(self, start_time_delta, duration_delta):
        # 检查start_time误差，前后波动最多conf['start_time_delta_limit']小时
        if abs(start_time_delta) > self.start_time_delta_limit:
            return False
        # 检查duration误差，前后波动最多conf['duration_delta_limit']小时
        if abs(duration_delta) > self.duration_delta_limit:
            return False
        # 检查duration，至少要自习3小时
        least_duration = 3600 * 3
        if (self.duration + duration_delta) < least_duration:
            return False
        return True

    def adjust_conf_randomly(self, random_range=0, factor=1.0, max_retry_time=100):
        border = round((random_range / 10) * 3600 * factor)
        retry_time = max_retry_time  # 尝试调整最多100次
        while retry_time > 0:
            # 随机生成一组调整
            valid_start_time_delta = round(randint(-border, border) / 3600) * 3600
            valid_duration_delta = round(randint(-2 * border, border) / 3600) * 3600
            # 限制valid_start_time_delta范围
            start_time_delta_lower_bound = get_start_time(7) - self.start_time  # 开始时间不早于7点
            start_time_delta_upper_bound = get_start_time(19) - self.start_time  # 开始时间不晚于19点
            valid_start_time_delta = min(valid_start_time_delta, start_time_delta_upper_bound)
            valid_start_time_delta = max(valid_start_time_delta, start_time_delta_lower_bound)
            # 限制valid_duration_delta范围
            duration_delta_upper_bound = get_start_time(22) - (
                    self.start_time + valid_start_time_delta) - self.duration  # 结束时间不超过22点
            valid_duration_delta = min(valid_duration_delta, duration_delta_upper_bound)
            # 检验结果是否可接受
            if self.is_time_affordable(valid_start_time_delta, valid_duration_delta):
                self.start_time_delta = valid_start_time_delta
                self.duration_delta = valid_duration_delta
                return
            retry_time -= 1
        logging.warning(f'自动调整时间失败，已尝试{max_retry_time}组')

    def login(self):
        data = {
            "login_name": self.username,
            "password": self.password,
            "ui_type": "com.Raw",
            "code": "ef4037d86e78f28fee8eca00d1a16e50",
            "str": "ViCRcuEKGnrVH3eM",
            "org_id": "142",
            "_ApplicationId": "lab4",
            "_JavaScriptKey": "lab4",
            "_ClientVersion": "js_xxx",
            "_InstallationId": "f28639d1-5c15-1fa0-89bd-9da5a8e015e0"
        }
        # POST login
        try:
            response = self.session.post(self.urls['login'], json=data, proxies=self.session.proxies)
        except requests.exceptions.ReadTimeout:
            logging.error('login页面超时无响应')
            return SeatBookerStatus.TIME_OUT
        except requests.exceptions.SSLError:
            logging.error('login页面post错误，怀疑是代理问题')
            return SeatBookerStatus.PROXY_ERROR
        # 处理login结果
        if response.status_code == 200:
            response_data = response.json()
            if "mobile" not in response_data.keys():
                logging.error("此账号未绑定手机，无法操作！")
                return SeatBookerStatus.LOGIN_FAILED
            if response_data["gender"] == "2":
                nick_name = f'美女<{response_data["name"]}>' if response_data["name"] != "刘庭华" else "<奥黛丽·刘·伊西娅·亦菲·赫本·庭华>"
            elif response_data["gender"] == "1":
                nick_name = f'帅哥<{response_data["name"]}>'
            else:
                nick_name = f'<{response_data["name"]}>'
            logging.info(f'{nick_name} ({self.username})，登录成功！')
            self.uid = response_data["org_score_info"]["uid"]
            return SeatBookerStatus.SUCCESS
        else:
            logging.error('登录失败，请检查config.json中账号和密码！')
            return SeatBookerStatus.LOGIN_FAILED

    def search_seat(self):
        data = {
            "beginTime": self.start_time + self.start_time_delta,
            "duration": self.duration + self.duration_delta,
            "num": 1,
            "space_category[category_id]": self.category_id,
            "space_category[content_id]": self.content_id
        }
        # POST search_seat
        try:
            response = self.session.post(self.urls['search_seat'], data=data, proxies=self.session.proxies)
        except requests.exceptions.ReadTimeout:
            logging.error('search_seat页面超时无响应')
            return SeatBookerStatus.TIME_OUT
        # 处理search_seat结果
        if response.status_code == 200:
            response_data = response.json()
            start_timestr, end_timestr = get_start_end_timestr(data["beginTime"], data["duration"])
            if "data" not in response_data.keys():
                logging.error(f'<{start_timestr}到{end_timestr}>在你选的教室没有符合条件的座位预约！')
                return SeatBookerStatus.NO_SEAT
            # 处理系统自动调整的时间
            if not response_data["content"]["children"][1]["ifAdjust"]:
                # 系统未自动调整时间
                logging.error(f'系统未自动调整时间，猜测是无需调整或位置不可用？')
            else:
                # 系统自动调整时间，如果太离谱就不接受
                valid_start_time = response_data["content"]["children"][1]["adjustDate"]
                valid_duration = response_data["content"]["children"][1]["adjustTime"]
                valid_start_timestr, valid_end_timestr = get_start_end_timestr(valid_start_time, valid_duration)
                logging.info(f'预期<{start_timestr}到{end_timestr}>，调整后<{valid_start_timestr}到{valid_end_timestr}>')
                valid_start_time_delta = valid_start_time - self.start_time
                valid_duration_delta = valid_duration - self.duration
                if not self.is_time_affordable(valid_start_time_delta, valid_duration_delta):
                    logging.error('系统提出的调整不可接受！')
                    return SeatBookerStatus.NOT_AFFORDABLE
                # 按照系统可用的时间更新预定时间
                self.start_time_delta = valid_start_time_delta
                self.duration_delta = valid_duration_delta
            # 开始选座
            if self.seat_id == 0:
                # 选系统推荐的座位
                self.target_seat = response_data["data"]["bestPairSeats"]["seats"][0]["id"]
                self.target_seat_title = response_data["data"]["bestPairSeats"]["seats"][0]["title"]
            else:
                # 选距离目标座位最近的一个座位，且最好是奇数
                min_abs = 1e10  # 初始值inf
                for seat in response_data["data"]["POIs"]:
                    cur_seat_title = int(seat['title'])
                    # 筛选出可选的位置中，距离目标座位最近的一个
                    if seat['state'] == 0 or seat['state'] == 2:
                        # state=0表示可选，state=2表示推荐
                        cur_abs = abs(cur_seat_title - self.seat_id)
                        if cur_abs == 0:
                            self.target_seat = seat['id']
                            self.target_seat_title = seat['title']
                            break  # 与预期座位一致，直接结束查找
                        if cur_abs < min_abs:
                            if min_abs - cur_abs > 10 or cur_seat_title % 2:
                                min_abs = cur_abs
                                self.target_seat = seat['id']
                                self.target_seat_title = seat['title']
            logging.info(f'不错不错，座位#{self.target_seat_title}可选，座位id{self.target_seat}！')
            return SeatBookerStatus.SUCCESS
        else:
            logging.error('GG，没座位选')
            return SeatBookerStatus.STATUS_CODE_ERROR

    def book_seat(self):
        data = {
            "beginTime": self.start_time + self.start_time_delta,
            "duration": self.duration + self.duration_delta,
            "seats[0]": self.target_seat,
            "seatBookers[0]": self.uid
        }
        # POST book_seat
        try:
            start_timestr, end_timestr = get_start_end_timestr(data["beginTime"], data["duration"])
            logging.info(f'发起订座申请{data["seats[0]"]}号，{start_timestr}到{end_timestr}')
            response_data = self.session.post(self.urls['book_seat'], data=data, proxies=self.session.proxies).json()
        except requests.exceptions.ReadTimeout:
            logging.error('book_seat页面超时无响应')
            return SeatBookerStatus.TIME_OUT
        # 处理book_seat结果
        if response_data["CODE"] == "ok":
            logging.info('估计不出意外是抢上宝座了！')
            return SeatBookerStatus.SUCCESS
        elif response_data["CODE"] == "ParamError":
            logging.error(f'{response_data["MESSAGE"]}')
            if "已有预约" in response_data["MESSAGE"]:
                return SeatBookerStatus.ALREADY_BOOKED
            return SeatBookerStatus.PARAM_ERROR
        else:
            logging.error('GG，不明原因预约失败')
            return SeatBookerStatus.UNKNOWN_ERROR

    def get_my_booking_list(self):
        # GET get_my_booking_list
        try:
            response_data = self.session.get(self.urls['get_my_booking_list'], proxies=self.session.proxies).json()
        except requests.exceptions.ReadTimeout:
            logging.error('get_my_booking_list页面超时无响应')
            return SeatBookerStatus.TIME_OUT
        # 处理get_my_booking_list结果
        if response_data["content"]["defaultItems"][0]["status"] != "0":
            logging.error('GG，好像没约上')
            return SeatBookerStatus.UNKNOWN_ERROR
        else:
            start_timestamp = int(response_data["content"]["defaultItems"][0]["time"])
            duration_sec = int(response_data["content"]["defaultItems"][0]["duration"])
            seat_num = response_data["content"]["defaultItems"][0]["seatNum"]
            room_name = response_data["content"]["defaultItems"][0]["roomName"]
            start_timestr, end_timestr = get_start_end_timestr(start_timestamp, duration_sec)
            logging.info(f'已预约！<{start_timestr}到{end_timestr}>在<{room_name}>的<{seat_num}号>座位自习，记得签到！')
            # 创建一个超时自动取消的任务
            create_auto_cancel_task(start_timestamp)
            logging.info('已创建定时任务，预约开始25分钟后还没签到就自动取消防止违约，前提是你那时候开着电脑……')
            return SeatBookerStatus.SUCCESS

    def cancel_booking(self):
        # 查询预约情况
        # GET get_my_booking_list
        try:
            response_data = self.session.get(self.urls['get_my_booking_list'], proxies=self.session.proxies).json()
        except requests.exceptions.ReadTimeout:
            logging.error('get_my_booking_list页面超时无响应')
            return SeatBookerStatus.TIME_OUT
        # 处理get_my_booking_list结果
        if response_data["content"]["defaultItems"][0]["status"] != "0":
            logging.error('没有可取消的预约？')
            return SeatBookerStatus.UNKNOWN_ERROR
        else:
            booking_id = response_data["content"]["defaultItems"][0]["id"]
            start_timestamp = int(response_data["content"]["defaultItems"][0]["time"])
            duration_sec = int(response_data["content"]["defaultItems"][0]["duration"])
            seat_num = response_data["content"]["defaultItems"][0]["seatNum"]
            room_name = response_data["content"]["defaultItems"][0]["roomName"]
            start_timestr, end_timestr = get_start_end_timestr(start_timestamp, duration_sec)
            logging.info(f'准备取消<{start_timestr}到{end_timestr}>在<{room_name}>的<{seat_num}号>座位预约！')
        # 开始取消预约
        cancel_booking_url = f'https://jxnu.huitu.zhishulib.com/Seat/Index/cancelBooking?bookingId={booking_id}&LAB_JSON=1'
        # POST cancel_booking
        try:
            response_data = self.session.post(cancel_booking_url, proxies=self.session.proxies).json()
        except requests.exceptions.ReadTimeout:
            logging.error('cancel_booking页面超时无响应')
            return SeatBookerStatus.TIME_OUT
        # 处理cancel_booking结果
        if response_data["CODE"] == "ok":
            logging.info("已成功取消预约！")
            return SeatBookerStatus.SUCCESS
        else:
            logging.error(response_data["MESSAGE"])
            return SeatBookerStatus.UNKNOWN_ERROR

    def loop_login(self, max_failed_time):
        # 若login失败可以循环重试，每2s一次，最多允许失败max_failed_time次
        failed_time = 0
        stat = self.login()
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 失败max_failed_time次以上退出login流程
            if failed_time > max_failed_time:
                logging.error(f'login已失败{max_failed_time}次')
                return SeatBookerStatus.LOOP_FAILED
            # 2秒重试
            time.sleep(2)
            # 如果是PROXY_ERROR，则修改代理
            if stat == SeatBookerStatus.PROXY_ERROR:
                proxy = {
                    'http': 'http://127.0.0.1:7890',
                    'https': 'http://127.0.0.1:7890',
                }
                self.session.proxies.update(proxy)
                logging.info('已自动修改代理为127.0.0.1:7890，适配clash用户')
            # 如果是LOGIN_FAILED，则退出登录流程
            elif stat == SeatBookerStatus.LOGIN_FAILED:
                return SeatBookerStatus.LOOP_FAILED
            stat = self.login()
        return SeatBookerStatus.SUCCESS

    def loop_search_seat(self, max_failed_time):
        # 若search_seat失败可以循环重试，每2s一次，最多允许失败max_failed_time次
        failed_time = 0
        stat = self.search_seat()
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 失败max_failed_time次以上退出search_seat流程
            if failed_time > max_failed_time:
                logging.error(f'search_seat已失败{max_failed_time}次')
                return SeatBookerStatus.LOOP_FAILED
            # 2秒重试
            time.sleep(2)
            # 无位置时大幅调整预定时间和时长
            if stat == SeatBookerStatus.NO_SEAT:
                self.adjust_conf_randomly(random_range=failed_time, factor=2.5, max_retry_time=200)
            # 系统调整的时间不可接受时小幅调整预定时间和时长
            elif stat == SeatBookerStatus.NOT_AFFORDABLE:
                self.adjust_conf_randomly(random_range=failed_time, factor=1.5, max_retry_time=100)
            stat = self.search_seat()
        return SeatBookerStatus.SUCCESS

    def loop_book_seat(self, max_failed_time):
        # 若book_seat失败可以循环重试，每2s一次，最多允许失败3次
        failed_time = 0
        stat = self.book_seat()
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 若已有预约，直接结束程序
            if stat == SeatBookerStatus.ALREADY_BOOKED:
                logging.info('已有预约，程序结束')
                exit(0)
            # 失败max_failed_time次以上退出程序
            if failed_time > max_failed_time:
                logging.error(f'book_seat已失败{max_failed_time}次')
                return SeatBookerStatus.LOOP_FAILED
            # 2秒重试
            time.sleep(2)
            stat = self.book_seat()
        return SeatBookerStatus.SUCCESS

    def loop_get_my_booking_list(self, max_failed_time):
        # 若get_my_booking_list失败可以循环重试，每2s一次，最多允许失败max_failed_time次
        failed_time = 0
        stat = self.get_my_booking_list()
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 失败max_failed_time次以上退出get_my_booking_list流程
            if failed_time > max_failed_time:
                logging.error(f'get_my_booking_list已失败{max_failed_time}次')
                return SeatBookerStatus.LOOP_FAILED
            # 2秒重试
            time.sleep(2)
            stat = self.get_my_booking_list()
        return SeatBookerStatus.SUCCESS


def booking_with_conf(conf):
    logging.info("--------欢迎使用图书馆自助订座系统  版权所有:YiqinXiong--------")
    if not conf:
        logging.error("无配置文件，请先使用“修改参数”脚本生成配置文件")
        exit(-1)
    # 实例化
    seat_booker = SeatBooker(conf)
    # login过程
    res_login = seat_booker.loop_login(max_failed_time=3)
    if res_login == SeatBookerStatus.LOOP_FAILED:
        exit(-1)
    # 总共尝试10次search_seat和book_seat的过程
    my_retry_time = 10
    while my_retry_time > 0:
        # 开始search_seat
        res_search_seat = seat_booker.loop_search_seat(max_failed_time=10)
        # 若search_seat大失败，直接重新尝试一轮
        if res_search_seat != SeatBookerStatus.SUCCESS:
            continue
        # 开始book_seat
        res_book_seat = seat_booker.loop_book_seat(max_failed_time=3)
        # 若成功则可以跳出 retry 的大循环
        if res_book_seat == SeatBookerStatus.SUCCESS:
            break
        # 重试机会减少
        time.sleep(2)
        my_retry_time -= 1
    # 最后获取用户预约信息
    seat_booker.loop_get_my_booking_list(max_failed_time=3)
    logging.info("--------------感谢使用图书馆自助订座系统   Byebye--------------")
