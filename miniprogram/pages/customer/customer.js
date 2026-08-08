const { request } = require('../../utils/request')

Page({
  data: { customer: null, note: '', saving: false },
  onLoad(options) { this.customerId = Number(options.id); this.load() },
  async load() {
    try { this.setData({ customer: await request(`/api/customers/${this.customerId}`) }) }
    catch (err) { wx.showToast({ title: err.message || '加载失败', icon: 'none' }) }
  },
  onNoteInput(e) { this.setData({ note: e.detail.value }) },
  async saveNote() {
    const content = this.data.note.trim()
    if (!content || this.data.saving) return
    this.setData({ saving: true })
    try {
      await request(`/api/customers/${this.customerId}/notes`, { method: 'POST', data: { content } })
      this.setData({ note: '' })
      await this.load()
      wx.showToast({ title: '已保存', icon: 'success' })
    } catch (err) { wx.showToast({ title: err.message || '保存失败', icon: 'none' }) }
    finally { this.setData({ saving: false }) }
  }
})
