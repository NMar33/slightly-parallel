'use strict'

const fs = require('node:fs')
const ts = require('../../frontend/node_modules/typescript')

const policyName = /^(?:.*(?:timeout|delay|interval|retries|threshold)(?:Ms|Seconds|S)?|port|limit|tries|size)$/i
const timerArgs = new Map([['setTimeout', 1], ['setInterval', 1], ['waitForTimeout', 0]])
const counts = {}

function numeric(node) {
  if (!node) return false
  if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken) node = node.operand
  return ts.isNumericLiteral(node) && ![0, 1].includes(Number(node.text.replaceAll('_', '')))
}

for (const path of JSON.parse(fs.readFileSync(0, 'utf8'))) {
  const file = ts.createSourceFile(path, fs.readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true)
  let count = 0
  function visit(node) {
    if (ts.isCallExpression(node)) {
      const callee = ts.isPropertyAccessExpression(node.expression) ? node.expression.name : node.expression
      const position = timerArgs.get(callee.getText(file))
      if (position !== undefined && numeric(node.arguments[position])) count++
    } else if (ts.isPropertyAssignment(node) || ts.isParameter(node) || ts.isVariableDeclaration(node)) {
      const name = ts.isIdentifier(node.name) || ts.isStringLiteral(node.name) ? node.name.text : ''
      if (!/^[A-Z][A-Z0-9_]+$/.test(name) && policyName.test(name) && numeric(node.initializer)) count++
    }
    ts.forEachChild(node, visit)
  }
  visit(file)
  counts[path] = count
}

process.stdout.write(JSON.stringify(counts))
