import vuetify from 'eslint-config-vuetify'

export default [
  {
    ignores: ['api/**', 'configs/**', 'telegram-bot/**', 'public/**'],
  },
  ...await vuetify(),
]
