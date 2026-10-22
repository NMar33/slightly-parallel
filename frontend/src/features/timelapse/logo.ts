import { useEffect, useState } from 'react'

/**
 * The operator's logo, decoded from its data URL. Only the latest URL's
 * image is kept: one that finishes loading after the logo was changed or
 * removed is dropped.
 */
export function useLogo(dataUrl: string): HTMLImageElement | null {
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  useEffect(() => {
    if (!dataUrl) {
      setImg(null)
      return
    }
    let current = true
    const el = new Image()
    el.onload = () => { if (current) setImg(el) }
    el.onerror = () => { if (current) setImg(null) }
    el.src = dataUrl
    return () => { current = false }
  }, [dataUrl])
  return img
}
