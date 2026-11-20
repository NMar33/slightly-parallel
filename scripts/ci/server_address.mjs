import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const defaults = require('../../backend/backend/server_defaults.json')

export const serverUrl = () => `http://${defaults.host}:${process.env.SP_PORT || defaults.port}`
