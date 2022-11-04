import datetime
import json
import time
from enum import Enum
from random import randint, sample
from guabookseat.models import UserCookie
from guabookseat.constants import Constants
from guabookseat import db, global_seat_map

import requests


def get_start_time(conf_start_time):
    # 获取今日0点时间戳
    today = datetime.date.today()
    today_timestamp = int(time.mktime(today.timetuple()))
    # 获取阈值时间戳，是当前时间戳和系统刷新时间戳中较小的一个
    now_timestamp = int(time.time())
    sys_timestamp = today_timestamp + 3600 * Constants.MAX_END_TIME
    threshold_timestamp = min(now_timestamp, sys_timestamp)
    # 若未到今日开始时间，则预约今日自习室，否则预约明日自习室
    today_start_time = today_timestamp + 3600 * conf_start_time
    if today_start_time > threshold_timestamp:
        return today_start_time
    else:
        return today_start_time + 86400


def get_penalty_time(failed_time, max_failed_time):
    # 基本间隔秒数
    penalty_base = 1
    # 最大罚时秒数
    penalty_max = 4
    # penalty_base秒重试，加上最多penalty_max秒的罚时（与失败次数正相关）
    return penalty_base + ((failed_time / max_failed_time) ** 2) * penalty_max


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
    EXCEED_TIME = 14


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
            'checkout_booking': url_home + '/Seat/Index/checkOut?LAB_JSON=1',
        }
        self.session = requests.session()
        self.session.headers.update(fake_header)
        # 设置cookie
        user_cookie = UserCookie.query.filter_by(username=self.username).first()
        if user_cookie:
            if user_cookie.is_expired():
                # 登录
                stat = self.loop_login(max_failed_time=2)
                if stat != SeatBookerStatus.SUCCESS:
                    raise RuntimeError("cookie过期且登陆失败")
                # 更新cookie
                user_cookie.set_cookie(self.session.cookies.get_dict(), self.username, self.uid)
                db.session.commit()
            else:
                # 使用保存的cookie
                self.session.cookies.update(user_cookie.get_cookie())
                self.uid = user_cookie.get_uid()
        else:
            # 登录
            stat = self.loop_login(max_failed_time=2)
            if stat != SeatBookerStatus.SUCCESS:
                raise RuntimeError("无cookie且登陆失败")
            # 保存cookie
            user_cookie = UserCookie()
            user_cookie.set_cookie(self.session.cookies.get_dict(), self.username, self.uid)
            db.session.add(user_cookie)
            db.session.commit()

    def set_target_seat(self):
        seat_map = global_seat_map.get_map()[str(self.content_id)] if global_seat_map else None
        if not seat_map:
            self.logger.warning(f"UID:{self.username} Empty SeatMap!")
            return SeatBookerStatus.UNKNOWN_ERROR
        seat_info = {'content_id': self.content_id}
        # 设置target_seat
        if self.seat_id == 0:
            # 随机选一个
            seat_title = sample(seat_map.keys(), 1)[0]
            seat_id = seat_map[seat_title]
            seat_info['seat_title'] = seat_title
            seat_info['seat_id'] = seat_id
        else:
            # 选指定位置
            if str(self.seat_id) not in seat_map:
                self.logger.warning(f"UID:{self.username} Not found target_seat in SeatMap!")
                return SeatBookerStatus.UNKNOWN_ERROR
            seat_id = seat_map[str(self.seat_id)]
            seat_info['seat_title'] = self.seat_id
            seat_info['seat_id'] = seat_id
        self.logger.info(f"UID:{self.username} seat_info:{seat_info}!")
        self.target_seat = str(seat_info['seat_id'])
        self.target_seat_title = str(seat_info['seat_title'])
        return SeatBookerStatus.SUCCESS

    def get_refresh_seat_map(self, content_id, max_retry_time=5):
        seat_map = {}
        data = {
            "beginTime": self.start_time,
            "duration": 10800,
            "num": 1,
            "space_category[category_id]": self.category_id,
            "space_category[content_id]": content_id
        }
        # POST search_seat
        retry_time = 0
        while retry_time <= max_retry_time:
            status, response_data = self.get_remote_response(url=self.urls['search_seat'], method="post", data=data)
            if status == SeatBookerStatus.SUCCESS:
                break
            retry_time += 1
        if status != SeatBookerStatus.SUCCESS:
            return seat_map, status
        # 处理search_seat结果
        if "data" not in response_data.keys():
            self.logger.error(f"UID:{self.username} UNKNOWN_ERROR {response_data}")
            return seat_map, SeatBookerStatus.UNKNOWN_ERROR
        else:
            res_data = response_data["data"]
        # 返回 {seat_title: seat_id} 字典
        for seat in res_data["POIs"]:
            seat_title = seat['title']
            seat_id = int(seat['id'])
            seat_map[seat_title] = seat_id
        return seat_map, SeatBookerStatus.SUCCESS

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
            start_time_delta_lower_bound = get_start_time(Constants.MIN_START_TIME) - self.start_time  # 开始时间下界
            start_time_delta_upper_bound = get_start_time(Constants.MAX_START_TIME) - self.start_time  # 开始时间上界
            valid_start_time_delta = min(valid_start_time_delta, start_time_delta_upper_bound)
            valid_start_time_delta = max(valid_start_time_delta, start_time_delta_lower_bound)
            # 限制valid_duration_delta范围
            duration_delta_upper_bound = get_start_time(Constants.MAX_END_TIME) - (
                    self.start_time + valid_start_time_delta) - self.duration  # 结束时间上界
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
                response = self.session.post(url=url, data=data, proxies=self.session.proxies, timeout=(4.05, 8.05))
            else:
                response = self.session.get(url=url, proxies=self.session.proxies, timeout=(4.05, 8.05))
        except requests.exceptions.ReadTimeout:
            self.logger.error(f"UID:{self.username} url:{url} {method} error:requests.exceptions.ReadTimeout")
            return SeatBookerStatus.TIME_OUT, None
        except requests.exceptions.SSLError:
            self.logger.error(f"UID:{self.username} url:{url} {method} error:requests.exceptions.SSLError")
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
        if "content" not in response_data.keys() or "children" not in response_data["content"].keys() or not \
                response_data["content"]["children"] or len(response_data["content"]["children"]) == 0:
            self.logger.error(f"UID:{self.username} UNKNOWN_ERROR {response_data}")
            return SeatBookerStatus.UNKNOWN_ERROR
        else:
            res_content_children = response_data["content"]["children"]
            if_adjust = res_content_children[0]["ifAdjust"]
            if_have = res_content_children[0]["ifHave"]
        # 无位置
        if "data" not in response_data.keys() or not if_have:
            return SeatBookerStatus.NO_SEAT
        else:
            res_data = response_data["data"]
        # 处理系统自动调整的时间
        if if_adjust:
            # 系统自动调整时间，如果太离谱就不接受
            valid_start_time = res_content_children[1]["adjustDate"]
            valid_duration = res_content_children[1]["adjustTime"]
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
            self.target_seat = res_data["bestPairSeats"]["seats"][0]["id"]
            self.target_seat_title = res_data["bestPairSeats"]["seats"][0]["title"]
        else:
            # 选距离目标座位最近的一个座位，且最好是奇数
            min_abs = 1e10  # 初始值inf
            for seat in res_data["POIs"]:
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
        else:
            if response_data["CODE"] == "ParamError":
                if "已有预约" in response_data["MESSAGE"]:
                    return SeatBookerStatus.ALREADY_BOOKED
                if "超出可预约时间范围" in response_data["MESSAGE"]:
                    self.logger.debug(f"UID:{self.username} EXCEED_TIME {response_data['MESSAGE']}!")
                    return SeatBookerStatus.EXCEED_TIME
                self.logger.warning(f"UID:{self.username} PARAM_ERROR {response_data['MESSAGE']}!")
                return SeatBookerStatus.PARAM_ERROR
            else:
                self.logger.warning(f"UID:{self.username} UNKNOWN_ERROR {response_data}!")
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

    def post_with_booking_id(self, url, booking_id):
        data = {
            'bookingId': str(booking_id),
        }
        # POST
        status, response_data = self.get_remote_response(url=url, method="post", data=data)
        if status != SeatBookerStatus.SUCCESS:
            return status
        if response_data["CODE"] == "ok":
            if ("result" not in response_data["DATA"]) or (response_data["DATA"]["result"] == "success"):
                return SeatBookerStatus.SUCCESS
            self.logger.error(f"UID:{self.username} booking_id:{booking_id} {response_data['DATA']['msg']}!")
            return SeatBookerStatus.NO_NEED
        else:
            self.logger.error(f"UID:{self.username} booking_id:{booking_id} {response_data['MESSAGE']}!")
            return SeatBookerStatus.NO_NEED

    def cancel_booking(self, booking_id):
        return self.post_with_booking_id(url=self.urls['cancel_booking'], booking_id=booking_id)

    def checkin_booking(self, booking_id):
        return self.post_with_booking_id(url=self.urls['checkin_booking'], booking_id=booking_id)

    def checkout_booking(self, booking_id):
        return self.post_with_booking_id(url=self.urls['checkout_booking'], booking_id=booking_id)

    def loop_login(self, max_failed_time):
        # 若login失败可以循环重试，最多允许失败max_failed_time次
        failed_time = 0
        stat = self.login()
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 失败max_failed_time次以上退出login流程
            if failed_time > max_failed_time:
                return SeatBookerStatus.LOOP_FAILED
            # 0.5秒重试
            time.sleep(0.5)
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
            # 重试等待
            time.sleep(get_penalty_time(failed_time=failed_time, max_failed_time=max_failed_time))
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
            # 若已有预约则结束程序，若参数错误则直接返回
            if stat == SeatBookerStatus.ALREADY_BOOKED or stat == SeatBookerStatus.PARAM_ERROR:
                self.logger.error(f"UID:{self.username} {stat.name}!")
                return stat
            # 失败max_failed_time次以上退出程序
            if failed_time > max_failed_time:
                self.logger.error(f"UID:{self.username} BOOK_SEAT FAILED!")
                return SeatBookerStatus.LOOP_FAILED
            # 重试等待
            time.sleep(get_penalty_time(failed_time=failed_time, max_failed_time=max_failed_time))
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
            # 重试等待
            time.sleep(get_penalty_time(failed_time=failed_time, max_failed_time=max_failed_time))
            stat, latest_record = self.get_latest_record()
        return SeatBookerStatus.SUCCESS, latest_record

    def loop_checkin_booking(self, booking_id, max_failed_time):
        # 若checkin_booking失败可以循环重试，每2s一次，最多允许失败max_failed_time次
        failed_time = 0
        stat = self.checkin_booking(booking_id=booking_id)
        while stat != SeatBookerStatus.SUCCESS:
            failed_time += 1
            # 无需签到
            if stat == SeatBookerStatus.NO_NEED:
                return stat
            # 失败max_failed_time次以上退出checkin_booking流程
            if failed_time > max_failed_time:
                return SeatBookerStatus.LOOP_FAILED
            # 重试等待
            time.sleep(get_penalty_time(failed_time=failed_time, max_failed_time=max_failed_time))
            stat = self.checkin_booking(booking_id=booking_id)
        return SeatBookerStatus.SUCCESS
