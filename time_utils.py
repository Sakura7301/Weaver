"""
时间相关工具函数
"""
import pytz
from datetime import datetime

def get_current_time_info(timezone="Asia/Shanghai"):
    """获取格式化的当前时间信息
    
    Args:
        timezone: 时区字符串，默认为"Asia/Shanghai"
    
    Returns:
        tuple: (time_info_dict, formatted_text)
    """
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    
    # 中文星期
    weekdays = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    weekday_cn = weekdays[now.weekday()]
    
    time_info = {
        "datetime": now.isoformat(),
        "date": now.strftime("%Y年%m月%d日"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": weekday_cn,
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "timestamp": int(now.timestamp())
    }
    
    # 格式化为易读文本
    formatted = f"""日期：{time_info['date']} {time_info['weekday']}\n时间：{time_info['time']}\n时区：{timezone}"""
    
    return time_info, formatted