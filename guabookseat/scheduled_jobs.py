import time

from flask_mail import Message

from guabookseat import scheduler, mail, app
from guabookseat.seatbooker.seat_booker import SeatBooker, SeatBookerStatus


def get_start_end_timestr(start_time, duration):
    start_timestr = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_time))
    end_timestr = time.strftime("%H:%M", time.localtime(start_time + duration))
    return start_timestr, end_timestr


def send_mail(title, body, receiver):
    msg = Message(subject=title, recipients=[receiver], body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
    with app.app_context():
        mail.send(msg)


def history_to_tuple(history):
    status_map = {
        "0": "已预约，等待签到",
        "1": "使用中",
        "3": "已结束，已签退结束",
        "4": "已取消",
        "5": "已结束，未签到结束",
        "6": "已结束，暂离未归结束",
        "7": "已结束，系统签退结束",
    }
    status = status_map.get(history.get("status"))
    status = status if status else "未知状态"
    start_timestamp = int(history.get("time"))
    duration_sec = int(history.get("duration"))
    seat_num = history.get("seatNum")
    room_name = history.get("roomName")
    start_timestr, end_timestr = get_start_end_timestr(start_timestamp, duration_sec)
    return status, start_timestr, end_timestr, room_name, seat_num


def call_seat_booker_func(conf, func_name, receiver=None, booking_id=None):
    if not conf or not func_name:
        return None
    # 实例化
    seat_booker = SeatBooker(conf, app.logger)
    # login过程
    res_login = seat_booker.loop_login(max_failed_time=3)
    if res_login == SeatBookerStatus.LOOP_FAILED:
        raise
    # 执行过程
    res = None
    if func_name == 'get_histories':
        _, res = seat_booker.get_my_histories()
        res = [history_to_tuple(history) for history in res]
    elif func_name == 'cancel_booking':
        stat, res = seat_booker.cancel_booking(booking_id)
        res = history_to_tuple(res)
        if stat == SeatBookerStatus.SUCCESS:
            # 发邮件（取消成功）
            if receiver and receiver != "":
                mail_tuple = res
                title = "[guaBookSeat] 自动取消预约成功！"
                body = f"若预约开始25分钟后还没签到，则会自动取消预约以防止违约。\n" \
                       f"已取消<{mail_tuple[1]}到{mail_tuple[2]}>在<{mail_tuple[3]}>的<{mail_tuple[4]}号>座位的预约！"
                send_mail(title, body, receiver)
    return res


def auto_booking(conf, receiver=None):
    if not conf:
        return
    student_id = conf["username"]
    # 实例化
    seat_booker = SeatBooker(conf, app.logger)
    # login过程
    res_login = seat_booker.loop_login(max_failed_time=3)
    if res_login == SeatBookerStatus.LOOP_FAILED:
        raise
    # 总共尝试10次search_seat和book_seat的过程
    already_booked = False
    retry_time = 10
    while retry_time > 0:
        try:
            # 开始search_seat
            res_search_seat = seat_booker.loop_search_seat(max_failed_time=10)
            # 若search_seat大失败，直接重新尝试一轮
            if res_search_seat != SeatBookerStatus.SUCCESS:
                continue
            # 开始book_seat
            res_book_seat = seat_booker.loop_book_seat(max_failed_time=3)
            # 若已有预约则退出
            if res_book_seat == SeatBookerStatus.ALREADY_BOOKED:
                already_booked = True
                break
            # 若成功则可以跳出 retry 的大循环
            if res_book_seat == SeatBookerStatus.SUCCESS:
                break
        except Exception as e:
            app.logger.critical(f"UID:{student_id} catch Exception in booking progress:\n{e}!")
            continue
        # 重试机会减少
        time.sleep(2)
        retry_time -= 1
    # 最后获取用户预约信息
    if not already_booked:
        res_booking, latest_record = seat_booker.loop_get_my_booking_list(max_failed_time=3)
        if res_booking == SeatBookerStatus.SUCCESS:
            # 创建定时取消任务
            job_id = 'cancel_booking_' + str(latest_record["id"])
            cancel_time = time.localtime(int(latest_record["time"]) + 60 * 25)  # 开始时间25分钟后如果还没签到就自动取消
            scheduler.add_job(id=job_id, func=call_seat_booker_func, trigger='date',
                              run_date=time.strftime("%Y-%m-%d %H:%M:%S", cancel_time),
                              args=[conf, 'cancel_booking', receiver, latest_record["id"]])
            app.logger.info(f"UID:{student_id} CREATE AUTO_CANCEL_JOB SUCCESS!")
            # 发邮件（成功）
            if receiver and receiver != "":
                mail_tuple = history_to_tuple(latest_record)
                title = "[guaBookSeat] 抢到座位啦！"
                body = f"已预约！<{mail_tuple[1]}到{mail_tuple[2]}>在<{mail_tuple[3]}>的<{mail_tuple[4]}号>座位自习，记得签到！" \
                       f"\n若预约开始25分钟后还没签到，则会自动取消预约以防止违约。"
                send_mail(title, body, receiver)
        else:
            app.logger.error(f"UID:{student_id} BOOK FAILED!")
            # 发邮件（失败）
            if receiver and receiver != "":
                title = "[guaBookSeat] 预约失败了，快看看啥情况..."
                body = f"您使用[guaBookSeat]预约位置失败了，请立即用小程序或[guaBookSeat]进行手动预约，并检查[guaBookSeat]的设置！" \
                       f"\n如有bug请与我（发件邮箱）联系。"
                send_mail(title, body, receiver)
    else:
        # 发邮件（已有预约）
        if receiver and receiver != "":
            title = "[guaBookSeat] 已有预约，本次预约无效..."
            body = f"如果实际没有预约，请立即用小程序或[guaBookSeat]进行手动预约，并检查[guaBookSeat]的设置！" \
                   f"\n如有bug请与我（发件邮箱）联系。"
            send_mail(title, body, receiver)
