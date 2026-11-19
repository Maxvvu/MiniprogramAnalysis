const config = require('./config')

// 只接受 HTTPS origin，不接受凭据、路径、查询、片段或反斜杠。
// 不依赖微信运行环境未必提供的全局 URL 类。
function buildApiUrl(path) {
  const base = config.API_BASE_URL
  if (typeof base !== 'string' ||
      !/^https:\/\/[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?\/?$/i.test(base)) {
    throw new Error('请先配置有效的 HTTPS 后端域名')
  }
  if (typeof path !== 'string' || !/^\/(?!\/)/.test(path) || /[\\\s#]/.test(path)) {
    throw new Error('无效的 API 路径')
  }
  return base.replace(/\/$/, '') + path
}

module.exports = { buildApiUrl }
