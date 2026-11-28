import{Z as c}from"./boot-DFLI_1ud.js";const l=1024,m=64,f=/^[a-z0-9]+(-[a-z0-9]+)*$/;function $(n){const t=n.trim();return t?t.length>m?c("Up to {n} characters.",{n:m}):f.test(t)?"":"Lower-case letters, digits and single hyphens. Up to 64 characters.":c("Type a name.")}function g(n){return n.length>l?c("Up to {n} characters.",{n:l}):""}function x(n){const t=(n??"").replace(/\r\n/g,`
`).trim();if(!t.startsWith(`---
`))return{name:"",description:"",extra:"",body:t};const e=t.indexOf(`
---`,4);if(e<0)return{name:"",description:"",extra:"",body:t};const r=t.slice(4,e),s=t.slice(e+4).replace(/^\n+/,""),[o,a]=d(r.split(`
`),"name"),[i,u]=d(a,"description");return{name:o,description:i,extra:u.join(`
`).trim(),body:s}}function d(n,t){const e=n.findIndex(i=>i.startsWith(`${t}:`));if(e<0)return["",n];let r=e+1;for(;r<n.length&&/^\s+\S/.test(n[r]);)r++;return[[n[e].slice(t.length+1).trim(),...n.slice(e+1,r).map(i=>i.trim())].join(" ").trim().replace(/^["'](.*)["']$/s,"$1").replace(/^[>|][-+]?\s*/,"").trim(),[...n.slice(0,e),...n.slice(r)]]}function p(n){const t=n.replace(/\s+/g," ").trim();return/^[\s"'[\]{}#&*!|>%@`]|: |\s#|:$|^(true|false|null|yes|no|on|off|~)$|^[-+]?\d/i.test(t)?JSON.stringify(t):t}function y({name:n,description:t,extra:e,body:r}){const s=e.trim();return`---
name: ${p(n)}
description: ${p(t)}
${s?`${s}
`:""}---

${r.trim()}
`}function M(n,t){const e=r=>r.replace(/\s+/g," ").trim();return e(n.name)===e(t.name)&&e(n.description)===e(t.description)&&n.extra.trim()===t.extra.trim()&&n.body.trim()===t.body.trim()}export{l as M,y as b,g as d,M as f,$ as n,x as s};
