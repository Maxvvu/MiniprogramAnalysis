# JWT 与 HTTPS 安全迁移

本次代码修改不会自动改变任何已部署的服务或已发布的小程序。合并和上线前需由部署负责人按以下顺序处理。

1. 确认生产域名、证书、当前运行版本与回滚方案。保留数据库及报告备份，不要把真实密钥、证书私钥或 .env 放入 Git、聊天或日志。
2. 在部署主机本地生成独立随机 JWT_SECRET，例如使用 `openssl rand -hex 32`，安全写入 backend/.env，Web 与 Worker 使用相同配置。新代码拒绝缺失、空白及不足 32 字节的密钥，旧默认值不再有效。长度检查不能代替随机性。
3. **轮换会使所有旧登录会话失效，用户必须重新登录。** 安排维护窗口并一次性更新所有 Web 实例；不要保留使用旧密钥的实例。不要为了回滚恢复已公开或可能泄露的旧密钥。
4. 配置同一宿主机上的 Nginx/Caddy，以有效证书在 443 终止 TLS，再转发到 127.0.0.1:8080。Docker 模板现在只绑定 127.0.0.1。部署模板与现有代理拓扑不同时，先审查拓扑，不要直接应用导致停机。
5. 经授权重新创建容器：`docker compose up -d --build --force-recreate`。仅 restart 不会更新 env_file 注入的环境变量。原生部署必须仅绑定回环地址并配置同等代理隔离。
6. 经授权调整防火墙/安全组，阻止公网直连 8080；保留必要管理通道。不要先发送凭据给 HTTP 再依赖重定向，重定向无法补救首次明文泄露。
7. 填写 miniprogram/utils/config.js 的真实 HTTPS origin（如 https://api.example.com，该示例不是可用服务），配置微信 request/downloadFile 合法域名，然后重新上传并发布小程序。默认留空是故意的安全关闭，未配置前无法登录或下载。
8. 验证 HTTPS 健康检查、有效证书、微信登录、客户分析及两种报告下载；验证旧 token 被拒绝、新登录可用、公网 8080 不可达。不要把 token 粘贴到命令历史或共享日志。

## 回归测试

```sh
python -m pip install python-dotenv
python -m unittest discover -s tests -p 'test_*.py'
node tests/transport.test.js
```

测试使用临时目录和虚构配置，不读取生产 .env、不访问外网。不代替微信真机和生产部署验证。
