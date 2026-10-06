import { useState } from 'react'
import { MAJOR_CLADES, OTHER, STATUS } from '../phylogenyStyle.js'

// The map key: clade colours and marks, foldable.
export default function Key({
  timeScaled,
  help = 'Drag to pan · scroll to move · ctrl/⌘ + scroll or pinch to zoom',
  startOpen = true,
}) {
  // Open on wide screens; folded on phones so it does not cover the tree.
  const [open, setOpen] = useState(() => startOpen && window.matchMedia('(min-width: 961px)').matches)
  return (
    <div className={open ? 'key open' : 'key'}>
      <button type="button" className="key-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        Key
      </button>
      {open && (
        <div className="key-body" aria-label="Key">
          <ul className="key-clades">
            {[...MAJOR_CLADES, OTHER].map((clade) => (
              <li key={clade.label}>
                <span className="swatch" style={{ background: clade.color }} aria-hidden="true" />
                {clade.label}
              </li>
            ))}
          </ul>
          <ul className="key-marks">
            <li>
              <span className="mark-symbol" style={{ color: STATUS.flagged.color }}>{STATUS.flagged.symbol}</span>
              Placement flagged (see the family's note)
            </li>
            <li>
              <span className="mark-symbol" style={{ color: STATUS.unknown.color }}>{STATUS.unknown.symbol}</span>
              Placement unknown
            </li>
            <li><span className="mark-symbol">†</span>Extinct</li>
            {timeScaled && (
              <>
                <li><span className="mark-bar" aria-hidden="true" />Fossil range of a group</li>
                <li><span className="mark-ghost" aria-hidden="true" />Lineage before its first fossil</li>
                <li><span className="mark-ci" aria-hidden="true" />95% range of a molecular date</li>
              </>
            )}
          </ul>
          <p className="key-help">{help}</p>
        </div>
      )}
    </div>
  )
}
