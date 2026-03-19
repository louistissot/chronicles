/**
 * CompassRose — draggable compass rose for map rotation.
 * Sits outside the rotated map container so it stays axis-aligned.
 * The needle counter-rotates by -rotation° to always point true north.
 */
import { memo, useCallback, useRef } from 'react'

interface CompassRoseProps {
  rotation: number
  onRotate: (degrees: number) => void
}

const SIZE = 80
const CENTER = SIZE / 2
const OUTER_R = 34
const INNER_R = 12

export default memo(function CompassRose({ rotation, onRotate }: CompassRoseProps) {
  const dragging = useRef(false)
  const svgRef = useRef<SVGSVGElement>(null)

  const getAngle = useCallback((clientX: number, clientY: number) => {
    const svg = svgRef.current
    if (!svg) return 0
    const rect = svg.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    const dx = clientX - cx
    const dy = clientY - cy
    // atan2 gives angle from positive X axis; we want angle from north (negative Y)
    const rad = Math.atan2(dx, -dy)
    return (rad * 180) / Math.PI
  }, [])

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragging.current = true
    ;(e.target as SVGElement).setPointerCapture(e.pointerId)
  }, [])

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return
    const angle = getAngle(e.clientX, e.clientY)
    // Normalize to 0-360
    onRotate(((angle % 360) + 360) % 360)
  }, [getAngle, onRotate])

  const handlePointerUp = useCallback(() => {
    dragging.current = false
  }, [])

  const handleDoubleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    onRotate(0)
  }, [onRotate])

  // Cardinal direction positions (at rotation=0, N is up)
  const cardinals = [
    { label: 'N', angle: 0, bold: true },
    { label: 'E', angle: 90, bold: false },
    { label: 'S', angle: 180, bold: false },
    { label: 'W', angle: 270, bold: false },
  ]

  return (
    <svg
      ref={svgRef}
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="select-none"
      style={{ cursor: dragging.current ? 'grabbing' : 'grab' }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onDoubleClick={handleDoubleClick}
    >
      {/* Background circle */}
      <circle cx={CENTER} cy={CENTER} r={OUTER_R + 4} fill="rgba(8,11,20,0.85)" stroke="rgba(212,175,55,0.25)" strokeWidth="1" />

      {/* Outer ring — rotates with the map */}
      <g transform={`rotate(${rotation}, ${CENTER}, ${CENTER})`}>
        <circle cx={CENTER} cy={CENTER} r={OUTER_R} fill="none" stroke="rgba(212,175,55,0.15)" strokeWidth="0.5" />

        {/* Tick marks */}
        {Array.from({ length: 12 }, (_, i) => {
          const angle = i * 30
          const rad = (angle * Math.PI) / 180
          const inner = OUTER_R - 4
          const outer = OUTER_R
          return (
            <line
              key={i}
              x1={CENTER + inner * Math.sin(rad)}
              y1={CENTER - inner * Math.cos(rad)}
              x2={CENTER + outer * Math.sin(rad)}
              y2={CENTER - outer * Math.cos(rad)}
              stroke="rgba(212,175,55,0.20)"
              strokeWidth={i % 3 === 0 ? '1' : '0.5'}
            />
          )
        })}
      </g>

      {/* Cardinal letters — always axis-aligned (don't rotate) */}
      {cardinals.map(({ label, angle, bold }) => {
        const rad = (angle * Math.PI) / 180
        const r = OUTER_R - 10
        return (
          <text
            key={label}
            x={CENTER + r * Math.sin(rad)}
            y={CENTER - r * Math.cos(rad)}
            textAnchor="middle"
            dominantBaseline="central"
            fill={bold ? 'rgba(212,175,55,0.90)' : 'rgba(212,175,55,0.45)'}
            fontSize={bold ? '11' : '8'}
            fontFamily="Cinzel, serif"
            fontWeight={bold ? '700' : '400'}
          >
            {label}
          </text>
        )
      })}

      {/* Needle — counter-rotates to always point true north */}
      <g transform={`rotate(${-rotation}, ${CENTER}, ${CENTER})`}>
        {/* North needle (gold) */}
        <polygon
          points={`${CENTER},${CENTER - INNER_R - 10} ${CENTER - 3},${CENTER} ${CENTER + 3},${CENTER}`}
          fill="rgba(212,175,55,0.80)"
        />
        {/* South needle (dark) */}
        <polygon
          points={`${CENTER},${CENTER + INNER_R + 10} ${CENTER - 3},${CENTER} ${CENTER + 3},${CENTER}`}
          fill="rgba(212,175,55,0.20)"
        />
        {/* Center dot */}
        <circle cx={CENTER} cy={CENTER} r="3" fill="rgba(212,175,55,0.60)" />
      </g>
    </svg>
  )
})
