
#!/bin/bash

# ============================================================================
# Python 应用进程管理脚本
# 用法: ./run.sh [start|stop|restart|status]
# ============================================================================

# 配置参数 ← 改这里
APP_FILE="app.py"                           # 启动文件名
APP_NAME="Weaver"                           # 应用名称（用于日志文件命名和进程搜索）
VENV_ACTIVATE="$HOME/alex/bin/activate"     # 虚拟环境路径，不使用则留空

# 以下不需要改
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="python3"
LOG_DIR="$APP_DIR/logs"
PID_FILE="$APP_DIR/.${APP_NAME}.pid"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============================================================================
# 函数定义
# ============================================================================

check_running() {
    local pid

    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "$pid"
            return 0
        else
            rm -f "$PID_FILE"
        fi
    fi

    pid=$(pgrep -f "${PYTHON_BIN} ${APP_FILE}" | head -n 1)
    if [ -n "$pid" ]; then
        echo "$pid"
        return 0
    fi

    return 1
}

start_process() {
    local pid

    if pid=$(check_running); then
        echo -e "${YELLOW}✓ 程序已运行，进程ID: $pid${NC}"
        return 0
    fi

    if [ ! -f "$APP_DIR/$APP_FILE" ]; then
        echo -e "${RED}✗ 错误: 找不到启动文件 $APP_DIR/$APP_FILE${NC}"
        exit 1
    fi

    # 检查虚拟环境（仅在配置了路径时）
    if [ -n "$VENV_ACTIVATE" ] && [ ! -f "$VENV_ACTIVATE" ]; then
        echo -e "${RED}✗ 错误: 找不到虚拟环境 $VENV_ACTIVATE${NC}"
        exit 1
    fi

    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
        echo -e "${GREEN}✓ 创建日志目录: $LOG_DIR${NC}"
    fi

    local date=$(date +%Y_%m_%d_%H%M%S)
    local log_file="$LOG_DIR/${APP_NAME}_${date}.log"

    cd "$APP_DIR" || exit 1

    # 根据是否配置虚拟环境选择启动方式
    if [ -n "$VENV_ACTIVATE" ]; then
        nohup bash -c "source ${VENV_ACTIVATE} && ${PYTHON_BIN} ${APP_FILE}" >> "$log_file" 2>&1 &
    else
        nohup ${PYTHON_BIN} ${APP_FILE} >> "$log_file" 2>&1 &
    fi
    local new_pid=$!

    echo "$new_pid" > "$PID_FILE"

    sleep 1

    if ps -p "$new_pid" > /dev/null 2>&1; then
        if [ -n "$VENV_ACTIVATE" ]; then
            echo -e "${GREEN}✓ 虚拟环境: $VENV_ACTIVATE${NC}"
        else
            echo -e "${GREEN}✓ 虚拟环境: 未使用${NC}"
        fi
        echo -e "${GREEN}✓ 程序已启动，进程ID: $new_pid${NC}"
        echo -e "${GREEN}✓ 日志文件: $log_file${NC}"
        return 0
    else
        echo -e "${RED}✗ 启动失败，请检查日志: $log_file${NC}"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop_process() {
    local pid

    pid=$(check_running)
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}✓ 程序未运行${NC}"
        rm -f "$PID_FILE"
        return 0
    fi

    echo -e "${YELLOW}→ 正在停止进程 $pid...${NC}"
    kill "$pid" 2>/dev/null

    local count=0
    while ps -p "$pid" > /dev/null 2>&1 && [ $count -lt 10 ]; do
        sleep 1
        count=$((count + 1))
    done

    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${YELLOW}→ 进程未响应，强制关闭...${NC}"
        kill -9 "$pid" 2>/dev/null
    fi

    rm -f "$PID_FILE"
    echo -e "${GREEN}✓ 程序已停止${NC}"
    return 0
}

restart_process() {
    echo -e "${YELLOW}→ 重启程序...${NC}"
    stop_process
    sleep 2
    start_process
}

show_status() {
    local pid

    if pid=$(check_running); then
        local uptime=$(ps -p "$pid" -o etime= | xargs)
        local mem=$(ps -p "$pid" -o rss= | xargs)
        mem=$((mem / 1024))

        echo -e "${GREEN}✓ 程序运行中${NC}"
        echo -e "  进程ID  : $pid"
        echo -e "  运行时长: $uptime"
        echo -e "  内存占用: ${mem} MB"

        local latest_log=$(ls -t "$LOG_DIR"/${APP_NAME}_*.log 2>/dev/null | head -1)
        if [ -n "$latest_log" ]; then
            echo -e "  日志文件: $latest_log"
            echo -e "  最新日志:"
            tail -n 5 "$latest_log" | sed 's/^/    /'
        fi
    else
        echo -e "${RED}✗ 程序未运行${NC}"
    fi
}

# ============================================================================
# 主程序
# ============================================================================

case "${1:-status}" in
    start)
        start_process
        ;;
    stop)
        stop_process
        ;;
    restart)
        restart_process
        ;;
    status)
        show_status
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        echo ""
        echo "命令说明:"
        echo "  start   - 启动程序"
        echo "  stop    - 停止程序"
        echo "  restart - 重启程序"
        echo "  status  - 显示程序状态（含最新5行日志）"
        exit 1
        ;;
esac

exit $?
