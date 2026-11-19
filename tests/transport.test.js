const assert = require('node:assert/strict')
const config = require('../miniprogram/utils/config')
const { buildApiUrl } = require('../miniprogram/utils/api-url')
const { request } = require('../miniprogram/utils/request')
let page
global.Page = value => { page = value }
require('../miniprogram/pages/report/report')
let calls, reads, toasts
global.wx = {
  getStorageSync: () => { reads++; return 'test-token' },
  request: opts => { calls.push(opts); opts.success({ statusCode: 200, data: {} }) },
  downloadFile: opts => { calls.push(opts); opts.complete() },
  showToast: () => { toasts++ },
  showLoading: () => {},
  hideLoading: () => {}
}
page.setData = value => Object.assign(page.data, value)
page.data.taskId = 1
async function main() {
  const initial = config.API_BASE_URL
  assert.equal(initial, '')
  for (const base of ['', 'http://example.com', 'http://127.0.0.1:8080',
    '//example.com', 'https://user@example.com', 'https://example.com/path',
    'https://example.com?x=1', 'https://example.com#x', 'https://example.com\\evil',
    ' https://example.com', null]) {
    config.API_BASE_URL = base
    calls = []; reads = 0; toasts = 0
    assert.throws(() => buildApiUrl('/api/health'))
    await assert.rejects(request('/api/auth/wx-login', { auth: false }))
    await assert.rejects(request('/api/me'))
    page.onDownload()
    page.onDownloadSolution()
    assert.equal(calls.length, 0)
    assert.equal(reads, 0)
    assert.equal(toasts, 2)
    assert.equal(page.data.downloading, false)
    assert.equal(page.data.downloadingSolution, false)
  }
  config.API_BASE_URL = 'https://api.example.com/'
  for (const path of ['//evil.com', 'https://evil.com', '/\\evil', '/a b', '/a#b', null]) {
    assert.throws(() => buildApiUrl(path))
  }
  calls = []; reads = 0
  assert.equal(buildApiUrl('/api/health'), 'https://api.example.com/api/health')
  await request('/api/me')
  assert.equal(calls[0].header.Authorization, 'Bearer test-token')
  await request('/api/auth/wx-login', { auth: false })
  assert.equal(calls[1].header.Authorization, undefined)
  page.onDownload()
  page.onDownloadSolution()
  assert.equal(calls[2].url, 'https://api.example.com/api/analysis/1/docx')
  assert.equal(calls[3].url, 'https://api.example.com/api/analysis/1/solution-docx')
  assert.equal(calls[2].header.Authorization, 'Bearer test-token')
  assert.equal(calls[3].header.Authorization, 'Bearer test-token')
  config.API_BASE_URL = initial
  console.log('Transport regression tests passed (requests and both downloads)')
}
main().catch(err => { console.error(err); process.exitCode = 1 })
