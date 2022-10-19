class Constants:
    valid_rooms = {
        36: '二楼南自习室(201)',
        35: '二楼北自习室(202)',
        31: '三楼南自习室(301)',
        37: '三楼北自习室(302)'
    }
    MIN_START_TIME = 7
    MAX_START_TIME = 19
    MAX_END_TIME = 22
    valid_start_times = [x for x in range(MIN_START_TIME, MAX_START_TIME + 1)]
    valid_start_time_delta_limits = [x for x in range(0, 5)]
    valid_duration_delta_limits = [x for x in range(0, 7)]
