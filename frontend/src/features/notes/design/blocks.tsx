/**
 * The rich blocks of a note — moved to the shared module the Notes page
 * draws with (../render/blocks). What stays here is the design round's
 * drawn stand-in for a screenshot, which the mock's notes name as `shot:…`.
 */

export * from '../render/blocks'

/** A drawn stand-in for a screenshot: six visibly different page layouts, in the theme's colours. */
export function MockShot({ src, small = false }: { src: string; small?: boolean }) {
  const kind = src.replace(/^shot:/, '')
  const box = 'rounded-[2px] bg-surface border border-border-subtle'
  const hi = 'rounded-[2px] bg-brand-glow border border-brand/50'
  const g = small ? 'gap-2 p-3' : 'gap-4 p-8'
  const body = (() => {
    switch (kind) {
      case 'list': return (
        <div className={`h-full grid grid-cols-[1fr_3fr] ${g}`}>
          <div className={`flex flex-col ${small ? 'gap-2' : 'gap-3'}`}>{[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className={`h-[12%] ${i === 1 ? hi : box}`} />)}</div>
          <div className={`${box} flex flex-col ${g}`}><div className="h-[14%] w-1/2 rounded-[2px] bg-brand/40" /><div className="flex-1 rounded-[2px] bg-elevated" /><div className="h-[22%] grid grid-cols-3 gap-2">{[0, 1, 2].map((i) => <div key={i} className="rounded-[2px] bg-elevated" />)}</div></div>
        </div>)
      case 'tiles': return <div className={`h-full grid grid-cols-3 grid-rows-2 ${g}`}>{[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className={`${i === 4 ? hi : box} flex flex-col justify-end p-2`}><div className="h-[60%] rounded-[2px] bg-elevated" /></div>)}</div>
      case 'feed': return <div className={`h-full flex flex-col ${g}`}>{[0, 1, 2, 3].map((i) => <div key={i} className={`flex-1 ${i === 0 ? hi : box} flex items-center gap-2 px-3`}><div className="h-[60%] aspect-square rounded-pill bg-elevated" /><div className="h-[25%] flex-1 rounded-[2px] bg-elevated" /></div>)}</div>
      case 'board': return <div className={`h-full grid grid-cols-3 ${g}`}>{[3, 2, 0].map((n, c) => <div key={c} className={`rounded-[2px] bg-elevated flex flex-col gap-2 p-2`}>{Array.from({ length: n }, (_, i) => <div key={i} className={`h-[22%] ${c === 0 && i === 0 ? hi : box}`} />)}</div>)}</div>
      case 'single': return <div className={`h-full flex items-center ${g}`}><div className="w-[6%] h-[20%] rounded-[2px] bg-elevated" /><div className={`flex-1 h-full ${hi} p-3 flex flex-col gap-2`}><div className="h-[55%] rounded-[2px] bg-surface" /><div className="h-[8%] w-2/3 rounded-[2px] bg-brand/40" /><div className="h-[8%] w-1/2 rounded-[2px] bg-surface" /></div><div className="w-[6%] h-[20%] rounded-[2px] bg-elevated" /></div>
      default: return <div className={`h-full flex flex-col ${small ? 'gap-1 p-3' : 'gap-2 p-8'}`}>{[0, 1, 2, 3, 4, 5, 6].map((i) => <div key={i} className={`flex-1 grid grid-cols-[2fr_1fr_1fr_3fr] gap-2 ${i === 0 ? '' : ''}`}>{[0, 1, 2, 3].map((c) => <div key={c} className={`rounded-[2px] ${i === 0 ? 'bg-border-default' : i === 3 && c === 0 ? 'bg-brand/40' : 'bg-elevated'}`} />)}</div>)}</div>
    }
  })()
  return <div data-shot={kind} className="aspect-[16/10] w-full rounded-input border border-border-default bg-base overflow-hidden">{body}</div>
}
