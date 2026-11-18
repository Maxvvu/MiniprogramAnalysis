// 部署前填入已配置有效证书的 HTTPS 域名；留空时所有 API 请求会安全失败。
// 不要填公网 HTTP 地址，也不要通过关闭 TLS 校验绕过此要求。
module.exports = {
  API_BASE_URL: ''
}
