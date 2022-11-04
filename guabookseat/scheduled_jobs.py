import time
import json
from flask_mail import Message

from guabookseat import scheduler, mail, app, global_seat_map
from guabookseat.seatbooker.seat_booker import SeatBooker, SeatBookerStatus
from guabookseat.constants import Constants


def get_start_end_timestr(start_time, duration):
    start_timestr = time.strftime("%Y-%m-%d %H:%M", time.localtime(start_time))
    end_timestr = time.strftime("%H:%M", time.localtime(start_time + duration))
    return start_timestr, end_timestr


def send_mail(title, body, receiver):
    if not receiver or type(receiver) != str or receiver == "":
        return
    msg = Message(subject=title, recipients=[receiver], body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
    try:
        with app.app_context():
            mail.send(msg)
    except Exception as e:
        app.logger.error(f"send_email raise an Exception:\n{e}")


def history_to_tuple(history):
    if not history:
        return None, None, None, None, None, None, None
    status_map = {
        "0": "已预约，等待签到",
        "1": "使用中",
        "3": "已结束，已签退结束",
        "4": "已取消",
        "5": "已结束，未签到结束",
        "6": "已结束，暂离未归结束",
        "7": "已结束，系统签退结束",
        "8": "预约邀请待确认",
    }
    status = status_map.get(history.get("status"))
    status = status if status else "未知状态"
    start_timestamp = int(history.get("time"))
    duration_sec = int(history.get("duration"))
    seat_num = history.get("seatNum")
    room_name = history.get("roomName")
    booking_id = history.get("id")
    start_timestr, end_timestr = get_start_end_timestr(start_timestamp, duration_sec)
    return status, start_timestr, end_timestr, room_name, seat_num, booking_id, start_timestamp


def call_seat_booker_func(conf, func_name, receiver=None, booking_id=None):
    if not conf or not func_name:
        app.logger.error(f"call_seat_booker_func not conf:{not conf} or not func_name: {not func_name}")
        return None
    # 实例化
    try:
        seat_booker = SeatBooker(conf, app.logger)
    except RuntimeError as e:
        app.logger.critical(f"SeatBooker: {str(e)}")
        raise e
    # 执行过程
    if func_name == 'get_histories':
        _, res = seat_booker.get_my_booking_list()
        res = [history_to_tuple(history) for history in res] if res else None
        return res
    elif func_name == 'checkin_booking':
        stat = seat_booker.loop_checkin_booking(booking_id=booking_id, max_failed_time=3)
        if stat == SeatBookerStatus.NO_NEED:
            return
        res = seat_booker.get_target_record(booking_id=booking_id)
        target_begin_time = int(res["time"]) if res else time.time() + 60 * 10
        if stat == SeatBookerStatus.SUCCESS:
            ''' 不需要自动签退，到时间后系统会自动签退
            # 创建定时签退任务
            job_id = 'checkout_booking_' + str(booking_id)
            target_end_time = target_begin_time + int(res["duration"])
            checkout_time = time.localtime(target_end_time)  # 自习结束时自动签退
            if not scheduler.get_job(id=job_id):
                scheduler.add_job(id=job_id, func=call_seat_booker_func, trigger='date',
                                  run_date=time.strftime("%Y-%m-%d %H:%M:%S", checkout_time),
                                  args=[conf, 'checkout_booking', receiver, booking_id])
                app.logger.info(f"UID:{conf['username']} CREATE AUTO_CHECKOUT_JOB SUCCESS!")
            '''
            # 发邮件（签到成功）
            mail_tuple = history_to_tuple(res)
            title = "[guaBookSeat] 自动签到成功！"
            body = f"已签到 [{mail_tuple[1]}] 到 [{mail_tuple[2]}] 在 [{mail_tuple[3]}] 的 " \
                   f"[{mail_tuple[4]}号] 座位！" \
                   f"\n卷爆他们！"
            send_mail(title, body, receiver)
        else:
            # 创建定时取消任务
            job_id = 'cancel_booking_' + str(booking_id)
            cancel_time = time.localtime(target_begin_time + 60 * 25)  # 开始时间25分钟后如果还没签到就自动取消
            if not scheduler.get_job(id=job_id):
                scheduler.add_job(id=job_id, func=call_seat_booker_func, trigger='date',
                                  run_date=time.strftime("%Y-%m-%d %H:%M:%S", cancel_time),
                                  args=[conf, 'cancel_booking', receiver, booking_id])
                app.logger.info(f"UID:{conf['username']} CREATE AUTO_CANCEL_JOB SUCCESS!")
            # 发邮件（签到失败）
            title = "[guaBookSeat] 自动签到失败！"
            body = f"还有{int(target_begin_time + 60 * 30 - time.time()) // 60}分钟签到，请尽快签到！" \
                   f"\n若预约开始25分钟后还没签到，则会自动取消预约以防止违约。" \
                   f"\n错误提示：{stat.name}" \
                   f"\n如有bug，请结合错误提示，并与我（发件邮箱）联系。"
            send_mail(title, body, receiver)
    elif func_name == 'cancel_booking':
        stat = seat_booker.cancel_booking(booking_id)
        if stat == SeatBookerStatus.NO_NEED:
            return
        res = seat_booker.get_target_record(booking_id=booking_id)
        if stat == SeatBookerStatus.SUCCESS:
            # 发邮件（取消成功）
            mail_tuple = history_to_tuple(res)
            title = "[guaBookSeat] 自动取消预约成功！"
            body = f"已取消 [{mail_tuple[1]}] 到 [{mail_tuple[2]}] 在 [{mail_tuple[3]}] 的 " \
                   f"[{mail_tuple[4]}号] 座位的预约！" \
                   f"\n若预约开始25分钟后还没签到，则会自动取消预约以防止违约。"
            send_mail(title, body, receiver)
        else:
            # 发邮件（取消失败）
            title = "[guaBookSeat] 自动取消预约失败！"
            body = f"还有5分钟签到，请尽快签到，或进入小程序手动取消预约！" \
                   f"\n错误提示：{stat.name}" \
                   f"\n如有bug，请结合错误提示，并与我（发件邮箱）联系。"
            send_mail(title, body, receiver)
    elif func_name == 'checkout_booking':
        stat = seat_booker.checkout_booking(booking_id)
        if stat == SeatBookerStatus.NO_NEED:
            return
        if stat == SeatBookerStatus.SUCCESS:
            # 发邮件（签退成功）
            res = seat_booker.get_target_record(booking_id=booking_id)
            mail_tuple = history_to_tuple(res)
            title = "[guaBookSeat] 自动签退成功！"
            body = f"已签退 [{mail_tuple[1]}] 到 [{mail_tuple[2]}] 在 [{mail_tuple[3]}] 的 " \
                   f"[{mail_tuple[4]}号] 座位！"
            send_mail(title, body, receiver)
        else:
            # 签退失败
            pass
    elif func_name == 'checkin_booking_immediately':
        stat = seat_booker.loop_checkin_booking(booking_id=booking_id, max_failed_time=3)
        return stat


def auto_booking(conf, receiver=None, max_retry_time=12):
    if not conf:
        app.logger.error(f"auto_booking not conf")
        return
    student_id = conf["username"]
    exception_msg = None
    # 实例化
    try:
        seat_booker = SeatBooker(conf, app.logger)
    except RuntimeError as e:
        app.logger.critical(f"SeatBooker: {str(e)}")
        exception_msg = "登录自习室失败，请检查订座信息中学号和自习室平台密码"
        # 发邮件（登陆失败）
        title = "[guaBookSeat] 预约失败了，快看看啥情况..."
        body = f"您使用[guaBookSeat]预约位置失败了，请立即用小程序或[guaBookSeat]进行手动预约，并检查[guaBookSeat]的设置！" \
               f"\n错误提示：{exception_msg}" \
               f"\n如有bug，请结合错误提示，并与我（发件邮箱）联系。"
        send_mail(title, body, receiver)
        return

    # 预设置target_seat以避免search_seat的高延迟
    res_set_target = seat_booker.set_target_seat()
    # 总共尝试max_retry_time次search_seat和book_seat的过程
    already_booked = False
    retry_time = 0
    while retry_time <= max_retry_time:
        try:
            # 前2次使用预设置的target_seat，跳过search_seat
            if retry_time > 1 or res_set_target != SeatBookerStatus.SUCCESS:
                # 开始search_seat
                res_search_seat = seat_booker.loop_search_seat(max_failed_time=5)
                # 若search_seat大失败，直接重新尝试一轮
                if res_search_seat != SeatBookerStatus.SUCCESS:
                    continue
            # 开始book_seat
            res_book_seat = seat_booker.loop_book_seat(max_failed_time=10)
            # 若已有预约则退出
            if res_book_seat == SeatBookerStatus.ALREADY_BOOKED:
                already_booked = True
                break
            # 若成功则可以跳出
            if res_book_seat == SeatBookerStatus.SUCCESS:
                break
        except Exception as e:
            app.logger.critical(f"UID:{student_id} raise an Exception in booking progress:\n{e}!")
            exception_msg = str(e)
        finally:
            retry_time += 1  # 重试次数增加
            time.sleep(2)

    # 最后获取用户预约信息并发邮件
    if not already_booked:
        status, latest_record = seat_booker.loop_get_latest_record(max_failed_time=10)
        if status != SeatBookerStatus.SUCCESS:
            app.logger.error(f"UID:{student_id} loop_get_latest_record failed:{status.name}!")
            return
        if latest_record["status"] == "0":
            # 创建定时签到任务
            job_id = 'checkin_booking_' + str(latest_record["id"])
            checkin_time_stamp = max(int(latest_record["time"]) - 60 * 10,
                                     int(time.time()) + 60 * 1)  # 提前10分钟或下1分钟，取较晚的一个
            checkin_time = time.localtime(checkin_time_stamp)  # 自动签到
            if not scheduler.get_job(id=job_id):
                scheduler.add_job(id=job_id, func=call_seat_booker_func, trigger='date',
                                  run_date=time.strftime("%Y-%m-%d %H:%M:%S", checkin_time),
                                  args=[conf, 'checkin_booking', receiver, latest_record["id"]])
            app.logger.info(f"UID:{student_id} CREATE AUTO_CHECKIN_JOB SUCCESS!")
            # 发邮件（成功）
            mail_tuple = history_to_tuple(latest_record)
            title = "[guaBookSeat] 抢到座位啦！"
            body = f"已预约！[{mail_tuple[1]}] 到 [{mail_tuple[2]}] 在 [{mail_tuple[3]}] 的 " \
                   f"[{mail_tuple[4]}号] 座位自习，自习开始前10分钟会自动签到。" \
                   f"\n若预约开始25分钟后还没签到，则会自动取消预约以防止违约。"
            send_mail(title, body, receiver)
        else:
            app.logger.error(f"UID:{student_id} BOOK FAILED!")
            # 发邮件（失败）
            title = "[guaBookSeat] 预约失败了，快看看啥情况..."
            body = f"您使用[guaBookSeat]预约位置失败了，请立即用小程序或[guaBookSeat]进行手动预约，并检查[guaBookSeat]的设置！" \
                   f"\n错误提示：{exception_msg}" \
                   f"\n如有bug，请结合错误提示，并与我（发件邮箱）联系。"
            send_mail(title, body, receiver)
    else:
        # 已有预约
        pass
    app.logger.info(f"UID:{student_id} auto_booking quit successfully!")


def refresh_map(conf_list):
    # 用任意一个可用的conf实例化SeatBooker
    seat_booker = None
    for each_conf in conf_list:
        conf = each_conf.get_config()
        # 实例化
        try:
            seat_booker = SeatBooker(conf, app.logger)
            break
        except RuntimeError:
            continue
    if not seat_booker:
        app.logger.error("No valid conf for SeatMap refresh_map, all of conf are login failed")
        return
    # 更新seat_map
    for content_id in Constants.valid_rooms.keys():
        seat_map, status = seat_booker.get_refresh_seat_map(content_id=content_id, max_retry_time=5)
        if status == SeatBookerStatus.SUCCESS:
            global_seat_map.map[str(content_id)].update(seat_map)
    # 写入json文件
    try:
        with open(global_seat_map.seat_map_file, 'w') as f:
            json.dump(global_seat_map.map, f)
    except IOError as e:
        app.logger.error(f"Write seat_map back to file failed (json.dump)! {e}")
