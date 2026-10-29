// Fidelity overlay: draws the ORIGINAL uploaded plan (cropped exactly as the
// backend cropped it) and paints the detected wall cells on top in
// translucent red. This lets the user verify the conversion is faithful to
// their exact image and tune threshold/density until it matches.

import { useEffect, useRef } from 'react'
import type { BuildingDetail } from '../types'

interface PlanOverlayProps {
  imageUrl: string
  cropBox: [number, number, number, number] // [left, top, right, bottom] source px
  building: BuildingDetail
  cellPx?: number
  /** true: show original image only; false: show image + detected walls */
  imageOnly?: boolean
}

export default function PlanOverlay({
  imageUrl,
  cropBox,
  building,
  cellPx = 14,
  imageOnly = false,
}: PlanOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    const img = new Image()
    img.onload = () => {
      const [left, top, right, bottom] = cropBox
      const sw = right - left
      const sh = bottom - top
      canvas.width = building.width * cellPx
      canvas.height = building.height * cellPx
      ctx.imageSmoothingEnabled = true
      // The source region cropped by the backend maps 1:1 onto the grid.
      ctx.drawImage(img, left, top, sw, sh, 0, 0, canvas.width, canvas.height)
      if (!imageOnly) {
        ctx.fillStyle = "rgba(225, 29, 72, 0.45)" // rose-600 translucent
        for (const [x, y] of building.walls) {
          ctx.fillRect(x * cellPx, y * cellPx, cellPx, cellPx)
        }
        ctx.strokeStyle = "rgba(225, 29, 72, 0.8)"
        ctx.lineWidth = 0.5
        for (const [x, y] of building.walls) {
          ctx.strokeRect(x * cellPx, y * cellPx, cellPx, cellPx)
        }
      }
    }
    img.src = imageUrl
  }, [imageUrl, cropBox, building, cellPx, imageOnly])

  return (
    <canvas
      ref={canvasRef}
      style={{ maxWidth: "100%", height: "auto", display: "block", borderRadius: 10 }}
      role="img"
      aria-label="Imported plan with detected walls overlaid"
    />
  )
}
