import { createApp } from 'vue'
import { Quasar, Notify, Dark } from 'quasar'
import '@quasar/extras/material-icons/material-icons.css'
import 'quasar/src/css/index.sass'

// Side-effect import: the UMD bundle registers the <reactive-dep-tree> custom element on
// window. It ships its own Vue 2 runtime, so it is independent of our Vue 3 app.
import 'reactive-dep-tree/dist/reactive-dep-tree.umd.js'

import App from './App.vue'

createApp(App).use(Quasar, { plugins: { Notify, Dark } }).mount('#app')
