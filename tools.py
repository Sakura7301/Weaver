"""
工具函数 - 增强版
"""
import os
import re
import json
import hashlib
import base64
import random
import string
import requests
import urllib3
import subprocess
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup
from log import logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============ 网络工具 ============

def fetch_webpage(url: str, timeout: int = 5) -> str:
    """爬取网页并提取文本内容"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        logger.debug(f"开始爬取: {url}")
        resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
        resp.encoding = resp.apparent_encoding

        soup = BeautifulSoup(resp.text, 'html.parser')

        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            tag.decompose()

        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        logger.debug(f"爬取成功，内容长度: {len(text)}")
        return text[:1500]
    except Exception as e:
        logger.error(f"爬取网页失败: {url} - {e}")
        return f"爬取失败: {str(e)}"


def web_search(query: str, max_results: int = 3) -> str:
    """搜索网络获取实时信息"""
    logger.info(f"执行搜索: {query}")

    searxng_url = os.getenv("SEARXNG_URL")
    if not searxng_url:
        logger.error("未配置 SEARXNG_URL")
        return "错误: 未配置 SEARXNG_URL"

    try:
        logger.debug(f"调用 SearXNG API: {searxng_url}")
        resp = requests.get(
            f"{searxng_url}/search",
            params={"q": query, "format": "json"},
            verify=False,
            timeout=10
        )

        data = resp.json()
        raw_results = data.get("results", [])

        if not raw_results:
            logger.warning("没有搜索结果")
            return "未找到相关结果"

        logger.debug(f"找到 {len(raw_results)} 条结果")

        output = f"搜索结果（关键词: {query}）:\n\n"

        for i, r in enumerate(raw_results[:max_results], 1):
            title = r.get('title', '无标题')
            url = r.get('url', '')
            snippet = r.get('content', '')[:150]

            output += f"{i}. {title}\n"
            output += f"   链接: {url}\n"
            output += f"   摘要: {snippet}\n\n"

            if i == 1:
                logger.debug(f"爬取详细内容: {title}")
                content = fetch_webpage(url)
                output += f"   详细内容:\n{content[:800]}\n\n"

        logger.info("搜索完成")
        return output

    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return f"搜索出错: {str(e)}"


def get_weather(city: str) -> str:
    """获取指定城市的天气信息"""
    logger.info(f"查询天气: {city}")
    try:
        # 使用 wttr.in 免费天气服务
        url = f"https://wttr.in/{city}?format=j1"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        current = data['current_condition'][0]
        location = data['nearest_area'][0]
        
        weather_desc = current['lang_zh'][0]['value'] if 'lang_zh' in current else current['weatherDesc'][0]['value']
        temp = current['temp_C']
        feels_like = current['FeelsLikeC']
        humidity = current['humidity']
        wind = current['windspeedKmph']
        
        result = f"📍 {location['areaName'][0]['value']} 当前天气\n"
        result += f"🌡️ 温度: {temp}°C (体感 {feels_like}°C)\n"
        result += f"☁️ 天气: {weather_desc}\n"
        result += f"💧 湿度: {humidity}%\n"
        result += f"💨 风速: {wind} km/h"
        
        return result
    except Exception as e:
        logger.error(f"获取天气失败: {e}")
        return f"获取天气失败: {str(e)}"


def get_ip_info(ip: str = "") -> str:
    """获取 IP 地址信息（留空获取本机公网IP）"""
    logger.info(f"查询 IP 信息: {ip or '本机'}")
    try:
        url = f"http://ip-api.com/json/{ip}?lang=zh-CN" if ip else "http://ip-api.com/json/?lang=zh-CN"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        
        if data['status'] == 'success':
            result = f"IP 信息查询结果:\n"
            result += f"IP: {data['query']}\n"
            result += f"国家: {data['country']} ({data['countryCode']})\n"
            result += f"地区: {data['regionName']}\n"
            result += f"城市: {data['city']}\n"
            result += f"运营商: {data['isp']}\n"
            result += f"时区: {data['timezone']}"
            return result
        else:
            return "IP 查询失败"
    except Exception as e:
        logger.error(f"IP查询失败: {e}")
        return f"IP查询失败: {str(e)}"


# ============ 时间日期工具 ============

def get_current_time() -> str:
    """获取当前日期和时间"""
    logger.debug("调用 get_current_time")
    return datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")


def date_calculator(date1: str, date2: str = "", operation: str = "diff") -> str:
    """
    日期计算器
    
    Args:
        date1: 日期，格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS
        date2: 第二个日期（可选，默认为今天）
        operation: 操作类型 - "diff"(计算差值), "add"(date1加天数), "sub"(date1减天数)
    """
    logger.info(f"日期计算: {date1}, {date2}, 操作: {operation}")
    
    try:
        # 解析日期
        if ' ' in date1:
            dt1 = datetime.strptime(date1, "%Y-%m-%d %H:%M:%S")
        else:
            dt1 = datetime.strptime(date1, "%Y-%m-%d")
        
        if operation == "diff":
            if date2:
                if ' ' in date2:
                    dt2 = datetime.strptime(date2, "%Y-%m-%d %H:%M:%S")
                else:
                    dt2 = datetime.strptime(date2, "%Y-%m-%d")
            else:
                dt2 = datetime.now()
            
            diff = abs(dt2 - dt1)
            days = diff.days
            hours, remainder = divmod(diff.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            return f"时间差: {days}天 {hours}小时 {minutes}分钟"
        
        elif operation == "add":
            days = int(date2) if date2 else 0
            result = dt1 + timedelta(days=days)
            return f"{date1} + {days}天 = {result.strftime('%Y-%m-%d %H:%M:%S')}"
        
        elif operation == "sub":
            days = int(date2) if date2 else 0
            result = dt1 - timedelta(days=days)
            return f"{date1} - {days}天 = {result.strftime('%Y-%m-%d %H:%M:%S')}"
        
        else:
            return "错误: 未知操作类型"
            
    except Exception as e:
        logger.error(f"日期计算失败: {e}")
        return f"日期计算失败: {str(e)}"


# ============ 数学计算工具 ============

def calculate(expression: str) -> str:
    """执行数学计算"""
    logger.debug(f"计算表达式: {expression}")
    try:
        # 允许的安全字符
        allowed_chars = set("0123456789+-*/().= <>!&|%^~")
        if not all(c in allowed_chars or c.isalpha() and c in 'sin cos tan log sqrt pi e abs round max min pow' for c in expression.replace(' ', '')):
            logger.warning(f"表达式包含非法字符: {expression}")
            return "错误: 表达式包含非法字符"

        # 使用 eval 计算（在安全限制下）
        safe_dict = {
            'sin': __import__('math').sin,
            'cos': __import__('math').cos,
            'tan': __import__('math').tan,
            'log': __import__('math').log,
            'sqrt': __import__('math').sqrt,
            'pi': __import__('math').pi,
            'e': __import__('math').e,
            'abs': abs,
            'round': round,
            'max': max,
            'min': min,
            'pow': pow
        }
        
        result = eval(expression, {"__builtins__": {}}, safe_dict)
        logger.debug(f"计算结果: {result}")
        return f"{expression} = {result}"
    except Exception as e:
        logger.error(f"计算失败: {expression} - {e}")
        return f"计算出错: {str(e)}"


def unit_convert(value: float, from_unit: str, to_unit: str) -> str:
    """
    单位换算器
    
    支持类型:
    - 长度: m, km, cm, mm, ft, in, mi
    - 重量: kg, g, mg, lb, oz, t
    - 温度: c, f, k (摄氏度,华氏度,开尔文)
    - 体积: l, ml, gal, oz_fl
    - 数据: b, kb, mb, gb, tb
    """
    logger.info(f"单位换算: {value} {from_unit} -> {to_unit}")
    
    try:
        # 长度换算（转换为米）
        length_factors = {
            'm': 1, 'km': 1000, 'cm': 0.01, 'mm': 0.001,
            'ft': 0.3048, 'in': 0.0254, 'mi': 1609.34,
            'yd': 0.9144
        }
        
        # 重量换算（转换为千克）
        weight_factors = {
            'kg': 1, 'g': 0.001, 'mg': 0.000001, 't': 1000,
            'lb': 0.453592, 'oz': 0.0283495
        }
        
        # 体积换算（转换为升）
        volume_factors = {
            'l': 1, 'ml': 0.001, 'gal': 3.78541, 'oz_fl': 0.0295735,
            'm3': 1000, 'cm3': 0.001
        }
        
        # 数据换算（转换为字节）
        data_factors = {
            'b': 1, 'kb': 1024, 'mb': 1024**2, 'gb': 1024**3, 'tb': 1024**4
        }
        
        from_unit = from_unit.lower()
        to_unit = to_unit.lower()
        
        result = None
        
        # 温度特殊处理
        if from_unit in ['c', 'f', 'k'] and to_unit in ['c', 'f', 'k']:
            # 先转为摄氏度
            if from_unit == 'c':
                c = value
            elif from_unit == 'f':
                c = (value - 32) * 5/9
            else:  # k
                c = value - 273.15
            
            # 再转为目标单位
            if to_unit == 'c':
                result = c
            elif to_unit == 'f':
                result = c * 9/5 + 32
            else:  # k
                result = c + 273.15
        
        # 长度换算
        elif from_unit in length_factors and to_unit in length_factors:
            meters = value * length_factors[from_unit]
            result = meters / length_factors[to_unit]
        
        # 重量换算
        elif from_unit in weight_factors and to_unit in weight_factors:
            kg = value * weight_factors[from_unit]
            result = kg / weight_factors[to_unit]
        
        # 体积换算
        elif from_unit in volume_factors and to_unit in volume_factors:
            liters = value * volume_factors[from_unit]
            result = liters / volume_factors[to_unit]
        
        # 数据换算
        elif from_unit in data_factors and to_unit in data_factors:
            bytes_val = value * data_factors[from_unit]
            result = bytes_val / data_factors[to_unit]
        
        if result is not None:
            return f"{value} {from_unit} = {result:.6g} {to_unit}"
        else:
            return f"错误: 不支持的单位换算 ({from_unit} -> {to_unit})"
            
    except Exception as e:
        logger.error(f"单位换算失败: {e}")
        return f"单位换算失败: {str(e)}"


# ============ 随机工具 ============

def random_generator(mode: str = "number", min_val: int = 1, max_val: int = 100, 
                    count: int = 1, length: int = 8, chars: str = "") -> str:
    """
    随机生成器
    
    Args:
        mode: 类型 - "number"(随机数), "choice"(随机选择), "password"(随机密码), "uuid"(UUID)
        min_val: 最小值（数字模式）
        max_val: 最大值（数字模式）
        count: 生成数量
        length: 密码长度（密码模式）
        chars: 可选字符集（密码模式，默认字母+数字）
    """
    logger.info(f"随机生成: mode={mode}")
    
    try:
        if mode == "number":
            results = [random.randint(min_val, max_val) for _ in range(count)]
            if count == 1:
                return f"随机数: {results[0]}"
            else:
                return f"随机数: {', '.join(map(str, results))}"
        
        elif mode == "choice":
            # 从逗号分隔的选项中随机选择
            options = [x.strip() for x in chars.split(',')] if chars else [str(i) for i in range(min_val, max_val+1)]
            if not options:
                return "错误: 没有可选项"
            choice = random.choice(options)
            return f"随机选择: {choice}"
        
        elif mode == "password":
            if not chars:
                chars = string.ascii_letters + string.digits + "!@#$%^&*"
            password = ''.join(random.choice(chars) for _ in range(length))
            return f"随机密码: {password}"
        
        elif mode == "uuid":
            # 生成 UUID v4
            uuid_str = ''.join([random.choice(string.hexdigits) for _ in range(32)])
            uuid_formatted = f"{uuid_str[:8]}-{uuid_str[8:12]}-{uuid_str[12:16]}-{uuid_str[16:20]}-{uuid_str[20:]}"
            return f"UUID: {uuid_formatted}"
        
        else:
            return "错误: 不支持的随机模式"
            
    except Exception as e:
        logger.error(f"随机生成失败: {e}")
        return f"随机生成失败: {str(e)}"


# ============ 文件操作工具 ============

def read_file(filepath: str, max_lines: int = 100) -> str:
    """
    读取文本文件内容
    
    Args:
        filepath: 文件路径（相对于当前目录或绝对路径）
        max_lines: 最大读取行数
    """
    logger.info(f"读取文件: {filepath}")
    
    try:
        # 安全检查：防止读取敏感文件
        dangerous_paths = ['/etc/passwd', '/etc/shadow', '.env', 'id_rsa']
        if any(d in filepath for d in dangerous_paths):
            return "错误: 禁止读取该文件"
        
        # 如果路径是相对路径，转换为绝对路径
        if not os.path.isabs(filepath):
            filepath = os.path.join(os.getcwd(), filepath)
        
        # 检查文件大小（限制 1MB）
        if os.path.getsize(filepath) > 1024 * 1024:
            return "错误: 文件过大（限制1MB）"
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[:max_lines]
            content = ''.join(lines)
            
        lines_count = len(lines)
        total_lines = sum(1 for _ in open(filepath, 'r', encoding='utf-8', errors='ignore'))
        
        result = f"文件: {filepath}\n"
        result += f"行数: {lines_count}/{total_lines}\n"
        result += f"内容:\n{'='*40}\n{content}\n{'='*40}"
        
        if total_lines > max_lines:
            result += f"\n(仅显示前 {max_lines} 行)"
        
        return result
        
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        return f"读取文件失败: {str(e)}"


def write_file(filepath: str, content: str, append: bool = False) -> str:
    """
    写入文本文件
    
    Args:
        filepath: 文件路径
        content: 文件内容
        append: 是否追加模式
    """
    logger.info(f"写入文件: {filepath}")
    
    try:
        # 安全检查
        if '..' in filepath or filepath.startswith('/etc'):
            return "错误: 禁止写入该路径"
        
        mode = 'a' if append else 'w'
        
        # 确保目录存在
        dir_path = os.path.dirname(filepath)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)
        
        with open(filepath, mode, encoding='utf-8') as f:
            f.write(content)
        
        action = "追加" if append else "写入"
        return f"{action}成功: {filepath} ({len(content)} 字符)"
        
    except Exception as e:
        logger.error(f"写入文件失败: {e}")
        return f"写入文件失败: {str(e)}"


def list_directory(path: str = ".") -> str:
    """列出目录内容"""
    logger.info(f"列出目录: {path}")
    
    try:
        if not os.path.exists(path):
            return f"错误: 路径不存在 {path}"
        
        if not os.path.isdir(path):
            return f"错误: 不是目录 {path}"
        
        items = os.listdir(path)
        result = f"目录: {os.path.abspath(path)}\n{'='*40}\n"
        
        files = []
        dirs = []
        
        for item in sorted(items):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                dirs.append(f"[DIR]  {item}")
            else:
                size = os.path.getsize(full_path)
                files.append(f"[FILE] {item} ({format_size(size)})")
        
        result += '\n'.join(dirs + files)
        result += f"\n{'='*40}\n共 {len(dirs)} 个目录, {len(files)} 个文件"
        
        return result
        
    except Exception as e:
        logger.error(f"列出目录失败: {e}")
        return f"列出目录失败: {str(e)}"


def format_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ============ 编解码工具 ============

def text_hash(text: str, algorithm: str = "md5") -> str:
    """
    计算文本哈希值
    
    Args:
        text: 要哈希的文本
        algorithm: 算法 - md5, sha1, sha256, sha512
    """
    logger.info(f"计算哈希: {algorithm}")
    
    try:
        algo = algorithm.lower()
        if algo == "md5":
            result = hashlib.md5(text.encode()).hexdigest()
        elif algo == "sha1":
            result = hashlib.sha1(text.encode()).hexdigest()
        elif algo == "sha256":
            result = hashlib.sha256(text.encode()).hexdigest()
        elif algo == "sha512":
            result = hashlib.sha512(text.encode()).hexdigest()
        else:
            return f"错误: 不支持的算法 {algorithm}"
        
        return f"{algorithm.upper()} 哈希值:\n{result}"
        
    except Exception as e:
        logger.error(f"哈希计算失败: {e}")
        return f"哈希计算失败: {str(e)}"


def base64_codec(text: str, operation: str = "encode") -> str:
    """
    Base64 编解码
    
    Args:
        text: 文本内容
        operation: encode 或 decode
    """
    logger.info(f"Base64 {operation}")
    
    try:
        if operation == "encode":
            result = base64.b64encode(text.encode()).decode()
            return f"Base64 编码结果:\n{result}"
        elif operation == "decode":
            result = base64.b64decode(text.encode()).decode()
            return f"Base64 解码结果:\n{result}"
        else:
            return "错误: operation 必须是 encode 或 decode"
            
    except Exception as e:
        logger.error(f"Base64 操作失败: {e}")
        return f"Base64 操作失败: {str(e)}"


def url_codec(text: str, operation: str = "encode") -> str:
    """
    URL 编解码
    
    Args:
        text: URL 或文本
        operation: encode 或 decode
    """
    from urllib.parse import quote, unquote
    logger.info(f"URL {operation}")
    
    try:
        if operation == "encode":
            result = quote(text, safe='')
            return f"URL 编码结果:\n{result}"
        elif operation == "decode":
            result = unquote(text)
            return f"URL 解码结果:\n{result}"
        else:
            return "错误: operation 必须是 encode 或 decode"
            
    except Exception as e:
        logger.error(f"URL 编解码失败: {e}")
        return f"URL 编解码失败: {str(e)}"


# ============ 文本处理工具 ============

def word_count(text: str) -> str:
    """统计文本字数、行数、字符数"""
    logger.info("统计文本")
    
    try:
        chars = len(text)
        chars_no_space = len(text.replace(' ', '').replace('\n', ''))
        words = len(text.split())
        lines = len(text.split('\n'))
        
        result = "文本统计:\n"
        result += f"字符数（含空格）: {chars}\n"
        result += f"字符数（不含空格）: {chars_no_space}\n"
        result += f"词数/字数: {words}\n"
        result += f"行数: {lines}"
        
        return result
        
    except Exception as e:
        logger.error(f"文本统计失败: {e}")
        return f"文本统计失败: {str(e)}"


def extract_links(text: str) -> str:
    """从文本中提取 URL 链接"""
    logger.info("提取链接")
    
    try:
        # 简单的 URL 正则匹配
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, text)
        
        if not urls:
            return "未找到 URL 链接"
        
        result = f"找到 {len(urls)} 个链接:\n"
        for i, url in enumerate(urls[:20], 1):  # 限制显示前20个
            result += f"{i}. {url}\n"
        
        if len(urls) > 20:
            result += f"... 还有 {len(urls) - 20} 个链接"
        
        return result
        
    except Exception as e:
        logger.error(f"提取链接失败: {e}")
        return f"提取链接失败: {str(e)}"


def text_replace(text: str, old: str, new: str, count: int = -1) -> str:
    """文本替换"""
    logger.info(f"文本替换: '{old}' -> '{new}'")
    
    try:
        if count > 0:
            result = text.replace(old, new, count)
        else:
            result = text.replace(old, new)
        
        replacements = text.count(old) if count < 0 else min(text.count(old), count)
        return f"替换完成（替换了 {replacements} 处）:\n{result}"
        
    except Exception as e:
        logger.error(f"文本替换失败: {e}")
        return f"文本替换失败: {str(e)}"


# ============ 系统信息工具 ============

def system_info() -> str:
    """获取系统信息"""
    logger.info("获取系统信息")
    
    try:
        import platform
        
        result = "系统信息:\n"
        result += f"操作系统: {platform.system()} {platform.release()}\n"
        result += f"机器名: {platform.node()}\n"
        result += f"处理器: {platform.processor()}\n"
        result += f"Python版本: {platform.python_version()}\n"
        result += f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        result += f"工作目录: {os.getcwd()}"
        
        return result
        
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        return f"获取系统信息失败: {str(e)}"


def ping_host(host: str, count: int = 4) -> str:
    """Ping 主机测试连通性"""
    logger.info(f"Ping {host}")
    
    try:
        import subprocess
        import platform
        
        system = platform.system().lower()
        if system == "windows":
            cmd = ["ping", "-n", str(count), host]
        else:
            cmd = ["ping", "-c", str(count), host]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            return f"Ping {host} 成功:\n{result.stdout[-500:]}"  # 只返回最后500字符
        else:
            return f"Ping {host} 失败:\n{result.stderr}"
            
    except Exception as e:
        logger.error(f"Ping 失败: {e}")
        return f"Ping 失败: {str(e)}"