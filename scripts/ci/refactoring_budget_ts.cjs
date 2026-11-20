'use strict'

const fs = require('node:fs')
const ts = require('../../frontend/node_modules/typescript')

const policyName = /^(?:.*(?:timeout|delay|interval|retries|threshold)(?:Ms|Seconds|S)?|port|limit|tries|size)$/i
const settingName = /_(?:NS|US|MS|S|SEC|SECS|SECONDS|MINUTES|HOURS|DAYS|BYTES|KB|MB|GB|PX|CHARS)$|(?:^|_)(?:MAX|MIN|COUNT|ATTEMPTS|TRIES|RETRIES|LIMIT|PORT|WORKERS|ROWS|ITEMS|ENTRIES|STEPS)(?:_|$)|(?:Ms|Seconds|Bytes|Count|Limit|Port|Attempts)$/
const timerArgs = new Map([['setTimeout', 1], ['setInterval', 1], ['waitForTimeout', 0]])
const counts = {}

function numeric(node) {
  if (!node) return false
  if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken) node = node.operand
  return ts.isNumericLiteral(node) && ![0, 1].includes(Number(node.text.replaceAll('_', '')))
}

for (const path of JSON.parse(fs.readFileSync(0, 'utf8'))) {
  const file = ts.createSourceFile(path, fs.readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true)
  const unnamed = new Set()
  function findBindings(node) {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) &&
        numeric(node.initializer) && !settingName.test(node.name.text)) {
      unnamed.add(node.name.text)
    }
    ts.forEachChild(node, findBindings)
  }
  findBindings(file)
  function policyValue(node) {
    return numeric(node) || Boolean(node && ts.isIdentifier(node) && unnamed.has(node.text))
  }

  let count = 0
  function visit(node) {
    if (ts.isCallExpression(node)) {
      const callee = ts.isPropertyAccessExpression(node.expression) ? node.expression.name : node.expression
      const position = timerArgs.get(callee.getText(file))
      if (position !== undefined && policyValue(node.arguments[position])) count++
    } else if (ts.isPropertyAssignment(node) || ts.isParameter(node) || ts.isVariableDeclaration(node)) {
      const name = ts.isIdentifier(node.name) || ts.isStringLiteral(node.name) ? node.name.text : ''
      const namedConstant = /^[A-Z][A-Z0-9_]+$/.test(name) && settingName.test(name)
      if (!namedConstant && policyName.test(name) && policyValue(node.initializer)) count++
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  counts[path] = count
}

process.stdout.write(JSON.stringify(counts))
