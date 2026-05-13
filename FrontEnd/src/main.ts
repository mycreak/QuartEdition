import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'
import { setupGuards } from './router/guards'

const zhCnOverride = {
  ...zhCn,
  el: {
    ...(zhCn as Record<string, unknown>).el,
    pagination: {
      ...((zhCn as Record<string, unknown>).el as Record<string, unknown>).pagination as Record<string, string>,
      total: '共计 {total} 条',
    },
  },
}

const app = createApp(App)

app.use(createPinia())
app.use(ElementPlus, { locale: zhCnOverride })

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

setupGuards(router)
app.use(router)

app.mount('#app')
