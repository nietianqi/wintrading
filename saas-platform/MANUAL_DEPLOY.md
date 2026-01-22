# 📋 手动部署指南 - CentOS Stream

服务器信息：
- IP: 43.161.216.248
- 用户: root
- 系统: CentOS Stream

---

## 步骤 1：连接服务器

在本地电脑打开终端：

```bash
ssh root@43.161.216.248
# 输入密码: ntq123!@#
```

---

## 步骤 2：安装依赖

复制并执行以下命令：

```bash
# 更新系统
yum update -y

# 安装基础工具
yum install -y git curl wget vim htop net-tools

# 安装 Docker
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 启动 Docker
systemctl start docker
systemctl enable docker

# 验证安装
docker --version
docker compose version

# 安装 Python 3
yum install -y python3 python3-pip
python3 --version
```

---

## 步骤 3：配置防火墙

```bash
# 安装防火墙
yum install -y firewalld
systemctl start firewalld
systemctl enable firewalld

# 开放端口
firewall-cmd --permanent --add-port=80/tcp
firewall-cmd --permanent --add-port=443/tcp
firewall-cmd --permanent --add-port=8000/tcp
firewall-cmd --permanent --add-port=8080/tcp
firewall-cmd --reload

# 验证
firewall-cmd --list-ports
```

---

## 步骤 4：下载项目代码

```bash
# 创建项目目录
mkdir -p /opt/hummingbot-saas
cd /opt/hummingbot-saas

# 克隆代码
git clone https://github.com/nietianqi/wintrading.git .

# 进入 saas-platform 目录
cd saas-platform
```

---

## 步骤 5：配置环境变量

```bash
# 复制配置文件
cp .env.example .env

# 生成密钥和密码
python3 << 'EOF'
import secrets, base64

print("\n=== 复制以下内容到 .env 文件 ===\n")
print(f"JWT_SECRET_KEY={secrets.token_urlsafe(32)}")
print(f"ENCRYPTION_MASTER_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}")
print(f"DB_PASSWORD={secrets.token_urlsafe(16)}")
print(f"REDIS_PASSWORD={secrets.token_urlsafe(16)}")
print("\n=== 复制结束 ===\n")
EOF

# 编辑 .env 文件
vi .env
```

在 vi 编辑器中：
1. 按 `i` 进入编辑模式
2. 找到以下行并替换：
   ```
   JWT_SECRET_KEY=<复制上面生成的值>
   ENCRYPTION_MASTER_KEY=<复制上面生成的值>
   ```
3. 在文件末尾添加：
   ```
   DB_PASSWORD=<复制上面生成的值>
   REDIS_PASSWORD=<复制上面生成的值>
   BASE_DOMAIN=43.161.216.248
   ADMIN_EMAIL=admin@example.com
   APP_ENV=production
   DEBUG=false
   ```
4. 按 `ESC`，输入 `:wq`，按 `Enter` 保存退出

---

## 步骤 6：创建数据目录

```bash
mkdir -p /srv/tenants
mkdir -p /srv/backups
chmod -R 755 /srv/tenants
chmod -R 755 /srv/backups
```

---

## 步骤 7：启动服务

```bash
# 创建 Docker 网络
docker network create web

# 启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps
```

---

## 步骤 8：等待数据库启动

```bash
# 等待 30 秒
sleep 30

# 检查数据库是否就绪
docker compose exec postgres pg_isready -U postgres
```

---

## 步骤 9：初始化数据库

```bash
# 创建 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 运行初始化脚本
python scripts/init_system.py
```

---

## 步骤 10：验证部署

```bash
# 测试 API
curl http://localhost:8000/health

# 查看日志
docker compose logs -f portal-api
```

---

## 步骤 11：在浏览器访问

打开浏览器，访问：
- API 文档: http://43.161.216.248:8000/docs
- Traefik 仪表盘: http://43.161.216.248:8080

默认管理员账号：
- 邮箱: admin@yourdomain.com
- 密码: changeme123

---

## 步骤 12：修改密码（重要！）

```bash
# 1. 修改服务器 root 密码
passwd
# 输入新密码两次

# 2. 修改管理员密码
# 访问 http://43.161.216.248:8000/docs
# 使用默认账号登录后修改密码
```

---

## 常用命令

```bash
# 查看所有服务
docker compose ps

# 查看日志
docker compose logs -f

# 重启服务
docker compose restart

# 停止服务
docker compose down

# 查看租户容器
docker ps | grep -E 'u[0-9]+'

# 进入 PostgreSQL
docker compose exec postgres psql -U postgres -d hummingbot_saas
```

---

## 故障排查

### 问题 1：端口被占用

```bash
# 查看占用端口的进程
netstat -tuln | grep 8000

# 停止占用的进程
kill -9 <PID>
```

### 问题 2：Docker 权限问题

```bash
# 添加当前用户到 docker 组
usermod -aG docker $USER

# 重新登录使生效
exit
ssh root@43.161.216.248
```

### 问题 3：防火墙阻止访问

```bash
# 临时关闭防火墙测试
systemctl stop firewalld

# 如果能访问，说明是防火墙问题
# 重新开放端口
firewall-cmd --permanent --add-port=8000/tcp
firewall-cmd --reload
systemctl start firewalld
```

---

## 测试部署

```bash
cd /opt/hummingbot-saas/saas-platform
bash test-deployment.sh
```

---

## 完成！

部署完成后，你可以：

1. 访问 API 文档: http://43.161.216.248:8000/docs
2. 注册第一个用户
3. 创建租户（会自动部署 Hummingbot）
4. 创建 Bot 并开始交易

祝你使用愉快！🎉
