#!/bin/bash

# 一键部署脚本

echo "================================"
echo "🎰 包子铺幸运大转盘 - 一键部署"
echo "================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker 未安装${NC}"
        echo "请先安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker 已安装${NC}"
}

# 检查 Docker Compose
check_docker_compose() {
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${YELLOW}⚠️  Docker Compose 未安装，尝试使用 docker compose${NC}"
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
    echo -e "${GREEN}✅ Docker Compose 可用${NC}"
}

# 构建镜像
build_image() {
    echo -e "\n${YELLOW}🔨 构建 Docker 镜像...${NC}"
    docker build -t lucky-wheel:latest . || {
        echo -e "${RED}❌ 镜像构建失败${NC}"
        exit 1
    }
    echo -e "${GREEN}✅ 镜像构建成功${NC}"
}

# 配置文件检查
check_config() {
    echo -e "\n${YELLOW}📝 检查配置文件...${NC}"
    
    if [ ! -f "config.py" ]; then
        if [ -f "config.prod.py" ]; then
            echo "复制生产环境配置..."
            cp config.prod.py config.py
        else
            echo -e "${RED}❌ 找不到配置文件${NC}"
            echo "请创建 config.py 文件"
            exit 1
        fi
    fi
    
    echo -e "${GREEN}✅ 配置文件就绪${NC}"
}

# 创建必要目录
create_dirs() {
    echo -e "\n${YELLOW}📁 创建必要目录...${NC}"
    mkdir -p data logs
    chmod 755 data logs
    echo -e "${GREEN}✅ 目录创建完成${NC}"
}

# 停止旧容器
stop_old_container() {
    echo -e "\n${YELLOW}🛑 停止旧容器...${NC}"
    docker stop lucky-wheel 2>/dev/null || true
    docker rm lucky-wheel 2>/dev/null || true
    echo -e "${GREEN}✅ 清理完成${NC}"
}

# 启动容器
start_container() {
    echo -e "\n${YELLOW}🚀 启动容器...${NC}"
    
    # 选择编排文件
    if [ -f "docker-compose.1panel.yml" ]; then
        COMPOSE_FILE="docker-compose.1panel.yml"
    else
        COMPOSE_FILE="docker-compose.yml"
    fi
    
    $DOCKER_COMPOSE -f $COMPOSE_FILE up -d || {
        echo -e "${RED}❌ 容器启动失败${NC}"
        exit 1
    }
    
    echo -e "${GREEN}✅ 容器启动成功${NC}"
}

# 检查服务状态
check_service() {
    echo -e "\n${YELLOW}🔍 检查服务状态...${NC}"
    
    # 等待服务启动
    sleep 5
    
    # 检查容器状态
    if docker ps | grep -q lucky-wheel; then
        echo -e "${GREEN}✅ 容器运行正常${NC}"
        
        # 获取容器IP和端口
        echo -e "\n${GREEN}🌐 访问信息：${NC}"
        echo "本地访问: http://localhost:15000"
        
        # 获取服务器公网IP（如果有）
        PUBLIC_IP=$(curl -s http://ipinfo.io/ip 2>/dev/null)
        if [ -n "$PUBLIC_IP" ]; then
            echo "公网访问: http://$PUBLIC_IP:15000"
        fi
        
        # 显示日志
        echo -e "\n${YELLOW}📋 最新日志：${NC}"
        docker logs --tail 20 lucky-wheel
    else
        echo -e "${RED}❌ 容器未运行${NC}"
        echo "查看错误日志："
        docker logs lucky-wheel
        exit 1
    fi
}

# 显示帮助信息
show_help() {
    echo -e "\n${GREEN}📚 部署完成！${NC}"
    echo "================================"
    echo "常用命令："
    echo "  查看日志: docker logs -f lucky-wheel"
    echo "  重启服务: docker restart lucky-wheel"
    echo "  停止服务: docker stop lucky-wheel"
    echo "  查看状态: docker ps | grep lucky-wheel"
    echo "================================"
    echo -e "${YELLOW}⚠️  注意事项：${NC}"
    echo "1. 请确保已修改 config.py 中的配置"
    echo "2. LinuxDo OAuth2 回调地址需要配置为实际域名"
    echo "3. 生产环境请修改 SECRET_KEY"
    echo "4. 建议配置 HTTPS 和反向代理"
    echo "================================"
}

# 主函数
main() {
    echo "开始部署..."
    
    check_docker
    check_docker_compose
    check_config
    create_dirs
    build_image
    stop_old_container
    start_container
    check_service
    show_help
}

# 执行主函数
main
