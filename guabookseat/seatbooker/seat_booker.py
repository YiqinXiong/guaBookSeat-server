import datetime
import json
import time
from enum import Enum
from random import randint

import requests


def get_start_time(conf_start_time):
    # 获取今日0点时间戳
    now_hour = datetime.datetime.now().hour
    today = datetime.date.today()
    today_timestamp = int(time.mktime(today.timetuple()))
    # 若今日未到22:00，则预约今日自习室，否则预约明日自习室
    return (today_timestamp + 3600 * conf_start_time) if now_hour < 22 else (
            today_timestamp + 86400 + 3600 * conf_start_time)


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
    JSON_DECODE_ERROR = 12
    NO_NEED = 13


# SeatBooker类
class SeatBooker:
    def __init__(self, conf, logger=None) -> None:
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
        # 日志
        self.logger = logger
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
            'get_my_booking_list': url_home + '/Seat/Index/myBookingList?LAB_JSON=1',
            'cancel_booking': url_home + '/Seat/Index/cancelBooking?LAB_JSON=1',
            'checkin_booking': url_home + '/Seat/Index/checkIn?LAB_JSON=1',
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

    def get_remote_response(self, url='', method='get', data=None):
        if method not in ("post", "get"):
            self.logger.error(f"UID:{self.username} url:{url} method:{method} not in (post, get)")

        # 尝试post/get
        try:
            if method == "post":
                response = self.session.post(url=url, data=data, proxies=self.session.proxies)
            else:
                response = self.session.get(url=url, proxies=self.session.proxies, timeout=5)
        except requests.exceptions.ReadTimeout:
            return SeatBookerStatus.TIME_OUT, None
        except requests.exceptions.SSLError:
            return SeatBookerStatus.PROXY_ERROR, None
        except Exception as e:
            self.logger.error(f"UID:{self.username} url:{url} {method} error:{str(e)}")
            return SeatBookerStatus.UNKNOWN_ERROR, None
        # 检查status_code
        if response.status_code != 200:
            self.logger.warning(f"UID:{self.username} url:{url} status_code != 200!")
            return SeatBookerStatus.STATUS_CODE_ERROR, None
        # 尝试解码response为response_data
        try:
            response_data = response.json()
        except requests.exceptions.JSONDecodeError:
            self.logger.error(f"UID:{self.username} url:{url} requests.exceptions.JSONDecodeError")
            return SeatBookerStatus.JSON_DECODE_ERROR, None
        except Exception as e:
            self.logger.error(f"UID:{self.username} url:{url} decode error:{str(e)}")
            return SeatBookerStatus.UNKNOWN_ERROR, None

        return SeatBookerStatus.SUCCESS, response_data

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
        status, response_data = self.get_remote_response(url=self.urls['login'], method="post", data=json.dumps(data))
        if status != SeatBookerStatus.SUCCESS:
            return status
        # 处理login结果
        if "mobile" not in response_data.keys():
            return SeatBookerStatus.LOGIN_FAILED
        self.uid = response_data["org_score_info"]["uid"]
        return SeatBookerStatus.SUCCESS

    def search_seat(self):
        data = {
            "beginTime": self.start_time + self.start_time_delta,
            "duration": self.duration + self.duration_delta,
            "num": 1,
            "space_category[category_id]": self.category_id,
            "space_category[content_id]": self.content_id
        }
        # POST search_seat
        status, response_data = self.get_remote_response(url=self.urls['search_seat'], method="post", data=data)
        if status != SeatBookerStatus.SUCCESS:
            return status
        # 处理search_seat结果
        if "data" not in response_data.keys():
            return SeatBookerStatus.NO_SEAT
        # 处理系统自动调整的时间
        if not response_data["content"]["children"][1]["ifAdjust"]:
            # 系统未自动调整时间
            pass
        else:
            # 系统自动调整时间，如果太离谱就不接受
            valid_start_time = response_data["content"]["children"][1]["adjustDate"]
            valid_duration = response_data["content"]["children"][1]["adjustTime"]
            valid_start_time_delta = valid_start_time - self.start_time
            valid_duration_delta = valid_duration - self.duration
            start_timestr = time.strftime("%m-%d %H:%M", time.localtime(self.start_time))
            valid_start_timestr = time.strftime("%m-%d %H:%M", time.localtime(valid_start_time))
            end_timestr = time.strftime("%H:%M", time.localtime(self.start_time + self.duration))
            valid_end_timestr = time.strftime("%H:%M", time.localtime(valid_start_time + valid_duration))
            self.logger.debug(f"UID:{self.username} "
                              f"target:<{start_timestr} to {end_timestr}> "
                              f"adjust:<{valid_start_timestr} to {valid_end_timestr}>!")
            if not self.is_time_affordable(valid_start_time_delta, valid_duration_delta):
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
        return SeatBookerStatus.SUCCESS

    def book_seat(self):
        data = {
            "beginTime": self.start_time + self.start_time_delta,
            "duration": self.duration + self.duration_delta,
            "seats[0]": self.target_seat,
            "seatBookers[0]": self.uid
        }
        # POST book_seat
        status, response_data = self.get_remote_response(url=self.urls['book_seat'], method="post", data=data)
        if status != SeatBookerStatus.SUCCESS:
            return status
        # 处理book_seat结果
        if response_data["CODE"] == "ok":
            return SeatBookerStatus.SUCCESS
        elif response_data["CODE"] == "ParamError":
            if "已有预约" in response_data["MESSAGE"]:
                return SeatBookerStatus.ALREADY_BOOKED
            return SeatBookerStatus.PARAM_ERROR
        else:
            return SeatBookerStatus.UNKNOWN_ERROR

    def get_latest_record(self):
        # GET get_my_booking_list
        status, response_data = self.get_remote_response(url=self.urls['get_my_booking_list'], method="get")
        if status != SeatBookerStatus.SUCCESS:
            return status, None
        return SeatBookerStatus.SUCCESS, response_data["content"]["defaultItems"][0]

    def get_my_booking_list(self):
        # GET get_my_booking_list
        status, response_data = self.get_remote_response(url=self.urls['get_my_booking_list'], method="get")
        if status != SeatBookerStatus.SUCCESS:
            return status, None
        return SeatBookerStatus.SUCCESS, response_data["content"]["defaultItems"]

    def get_target_record(self, booking_id):
        # 查询预约情况
        status, last_10_records = self.get_my_booking_list()
        if status != SeatBookerStatus.SUCCESS:
            return None
        # 找到目标记录
        target_record = None
        for record in last_10_records:
            if record.get("id") == booking_id:
                target_record = record
                break
        return target_record

    def cancel_booking(self, booking_id):
        target_record = self.get_target_record(booking_id)
        # 处理target_record结果
        if target_record is None or target_record["status"] != "0":
            self.logger.warning(
                f"UID:{self.username} booking_id:{booking_id} target_record is None：{target_record is None} or "
                f"target_record[status]!=0: {target_record['status'] if target_record else None}") 
            return SeatBookerStatus.NO_NEED, target_record
        # 开始取消预约
        data = {
            'bookingId': str(booking_id),
        }
        # POST cancel_booking
        status, response_data = self.get_remote_response(url=self.urls['cancel_booking'], method="post", data=data)
        if status != SeatBookerStatus.SUCCESS:
            return status, target_record
        # 处理cancel_booking结果
        if response_data["CODE"] == "ok":
            return SeatBookerStatus.SUCCESS, target_record
        else:
            return SeatBookerStatus.UNKNOWN_ERROR, target_record

    def checkin_booking(self, booking_id):
        target_record = self.get_target_record(booking_id)
        # 处理target_record结果
        if target_record is None or target_record["status"] != "0":
            self.logger.warning(
                f"UID:{self.username} booking_id:{booking_id} target_record is None：{target_record is None} or "
                f"target_record[status]!=0: {target_record['status'] if target_record else None}") 
            return SeatBookerStatus.NO_NEED, target_record
        # 开始签到
        data = {
            'bookingId': str(booking_id),
        }
        # POST checkin_booking
        status, response_data = self.get_remote_response(url=self.urls['checkin_booking'], method="post", data=data)
        if status != SeatBookerStatus.SUCCESS:
            return status, target_record
        # 处理checkin_booking结果
        if response_data["DATA"]["result"] == "success":
            return SeatBookerStatus.SUCCESS, target_record
        else:
            self.logger.error(f"UID:{self.username} booking_id:{booking_id} {response_data['DATA']['msg']}!")
            return SeatBookerStatus.UNKNOWN_ERROR, target_record

    def loop_login(self, max_failed_time):
        # 若login失败可以循环重试，每2s一次，最多允许失败max_failed_time次
        failed_time = 0
        stat = self.login()
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 失败max_failed_time次以上退出login流程
            if failed_time > max_failed_time:
                return SeatBookerStatus.LOOP_FAILED
            # 2秒重试，加上最多5s的罚时（与失败次数正相关）
            time.sleep(2 + ((failed_time / max_failed_time) ** 2) * 5)
            # 如果是PROXY_ERROR，则修改代理
            if stat == SeatBookerStatus.PROXY_ERROR:
                proxy = {
                    'http': 'http://127.0.0.1:7890',
                    'https': 'http://127.0.0.1:7890',
                }
                self.session.proxies.update(proxy)
            # 如果是LOGIN_FAILED，则退出登录流程
            elif stat == SeatBookerStatus.LOGIN_FAILED:
                self.logger.error(f"UID:{self.username} LOGIN FAILED!")
                return SeatBookerStatus.LOOP_FAILED
            stat = self.login()
        self.logger.info(f"UID:{self.username} LOGIN SUCCESS!")
        return SeatBookerStatus.SUCCESS

    def loop_search_seat(self, max_failed_time):
        # 若search_seat失败可以循环重试，每2s一次，最多允许失败max_failed_time次
        failed_time = 0
        stat = self.search_seat()
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 失败max_failed_time次以上退出search_seat流程
            if failed_time > max_failed_time:
                self.logger.error(f"UID:{self.username} SEARCH_SEAT FAILED!")
                return SeatBookerStatus.LOOP_FAILED
            # 2秒重试，加上最多5s的罚时（与失败次数正相关）
            time.sleep(2 + ((failed_time / max_failed_time) ** 2) * 5)
            # 无位置时大幅调整预定时间和时长
            if stat == SeatBookerStatus.NO_SEAT:
                self.logger.debug(f"UID:{self.username} SEARCH_SEAT NO_SEAT!")
                self.adjust_conf_randomly(random_range=failed_time, factor=2.5, max_retry_time=200)
            # 系统调整的时间不可接受时小幅调整预定时间和时长
            elif stat == SeatBookerStatus.NOT_AFFORDABLE:
                self.logger.debug(f"UID:{self.username} SEARCH_SEAT NOT_AFFORDABLE!")
                self.adjust_conf_randomly(random_range=failed_time, factor=1.5, max_retry_time=100)
            stat = self.search_seat()
        self.logger.info(f"UID:{self.username} valid_seat:#{self.target_seat_title} seat_id:{self.target_seat}!")
        return SeatBookerStatus.SUCCESS

    def loop_book_seat(self, max_failed_time):
        # 若book_seat失败可以循环重试，每2s一次，最多允许失败max_failed_time次
        failed_time = 0
        stat = self.book_seat()
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 若已有预约，直接结束程序
            if stat == SeatBookerStatus.ALREADY_BOOKED:
                self.logger.error(f"UID:{self.username} ALREADY_BOOKED!")
                return SeatBookerStatus.ALREADY_BOOKED
            # 失败max_failed_time次以上退出程序
            if failed_time > max_failed_time:
                self.logger.error(f"UID:{self.username} BOOK_SEAT FAILED!")
                return SeatBookerStatus.LOOP_FAILED
            # 2秒重试，加上最多5s的罚时（与失败次数正相关）
            time.sleep(2 + ((failed_time / max_failed_time) ** 2) * 5)
            stat = self.book_seat()
        self.logger.info(f"UID:{self.username} BOOK_SEAT SUCCESS!")
        return SeatBookerStatus.SUCCESS

    def loop_get_latest_record(self, max_failed_time):
        # 若get_latest_record失败可以循环重试，每2s一次，最多允许失败max_failed_time次
        failed_time = 0
        stat, latest_record = self.get_latest_record()
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 失败max_failed_time次以上退出get_latest_record流程
            if failed_time > max_failed_time:
                return SeatBookerStatus.LOOP_FAILED, None
            # 2秒重试，加上最多5s的罚时（与失败次数正相关）
            time.sleep(2 + ((failed_time / max_failed_time) ** 2) * 5)
            stat, latest_record = self.get_latest_record()
        return SeatBookerStatus.SUCCESS, latest_record

    def loop_checkin_booking(self, booking_id, max_failed_time):
        # 若checkin_booking失败可以循环重试，每2s一次，最多允许失败max_failed_time次
        failed_time = 0
        stat, target_record = self.checkin_booking(booking_id=booking_id)
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 无需签到
            if stat == SeatBookerStatus.NO_NEED:
                return stat, target_record
            # 失败max_failed_time次以上退出checkin_booking流程
            if failed_time > max_failed_time:
                return SeatBookerStatus.LOOP_FAILED, target_record
            # 2秒重试，加上最多5s的罚时（与失败次数正相关）
            time.sleep(2 + ((failed_time / max_failed_time) ** 2) * 5)
            stat, target_record = self.checkin_booking(booking_id=booking_id)
        return SeatBookerStatus.SUCCESS, target_record
