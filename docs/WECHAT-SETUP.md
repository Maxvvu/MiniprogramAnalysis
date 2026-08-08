# 微信小程序配置指南

## 1. 获取 AppID 与 AppSecret

1. 登录 [微信公众平台](https://mp.weixin.qq.com)（用你的个人主体小程序账号）
2. 「开发管理 → 开发设置」页面可看到 **AppID**
3. 同页面生成 **AppSecret**（只显示一次，妥善保存）
4. 填入后端 `backend/.env`：

```
WX_APPID=wx1234567890abcdef
WX_SECRET=你的AppSecret
```

## 2. 配置小程序项目

1. 打开微信开发者工具 → 导入项目 → 选择 `miniprogram/` 目录
2. AppID 填你自己的（不要选测试号，测试号无法调用 wx.login 换取 openid）
3. 修改 `miniprogram/utils/config.js` 中的 `API_BASE_URL` 为你的后端地址
4. 详情 → 本地设置 → 勾选「不校验合法域名…」（开发阶段必须）

## 3. 正式发布的域名要求

正式体验版/正式版只能请求 HTTPS 备案域名：

1. 准备已 ICP 备案的域名，配好 HTTPS 证书
2. 微信公众平台 →「开发管理 → 开发设置 → 服务器域名」→ `request 合法域名` 与 `downloadFile 合法域名` 都填 `https://你的域名`
3. 把 `utils/config.js` 改为该 HTTPS 地址

## 4. 个人主体小程序的能力边界

- 微信登录（wx.login）、内容展示、文件下载：**均可正常使用**
- 微信支付、获取用户手机号：需要企业主体，本应用未使用这些能力，不受影响

## 5. 验证清单

- [ ] `/api/health` 返回 `wx_configured: true`
- [ ] 开发者工具中点击「微信一键登录」成功进入分析页
- [ ] 提交一个客户（如"新东方"）能看到分析进度与报告
- [ ] 「下载 Word 报告」可正常打开 docx
