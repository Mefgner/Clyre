/**
 * plugins/vuetify.ts
 *
 * Framework documentation: https://vuetifyjs.com`
 */

// Composables
import { createVuetify } from 'vuetify'
import { md3 } from 'vuetify/blueprints'

// Styles
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

// https://vuetifyjs.com/en/introduction/why-vuetify/#feature-guides
export default createVuetify({
  defaults: {
    VBtn: {
      ripple: false,
      elevation: 0,
    },
    VListItem: {
      ripple: false,
      elevation: 0,
    },
  },
  theme: {
    defaultTheme: 'system',
  },
  blueprint: md3,
})
