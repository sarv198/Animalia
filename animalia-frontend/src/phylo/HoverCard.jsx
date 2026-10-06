import { STATUS } from '../phylogenyStyle.js'
import { ageSummary, displayName, photoCredit } from './labels.js'

// The compact card that follows the pointer: the animal comes into focus for
// families; clades and groups show their age.
export default function HoverCard({ node, x, y, stageWidth }) {
  const d = node.data
  const species = d.kind === 'family' ? d.representative_species : null
  const image = species?.image
  const flag = d.kind === 'family' ? STATUS[d.placement_status] : null
  const flip = x > stageWidth - 340
  return (
    <div
      className="hover-card"
      style={{ left: flip ? x - 316 : x + 18, top: y + 18 }}
      role="status"
    >
      {image && (
        <div className="hover-photo">
          <img src={image.thumbnail_url || image.url} alt="" referrerPolicy="no-referrer" />
        </div>
      )}
      <div className="hover-text">
        {species?.common_name && <p className="hover-common">{species.common_name}</p>}
        {species && <p className="hover-scientific">{species.scientific_name}</p>}
        <p className={species ? 'hover-family' : 'hover-title'}>{displayName(d)}</p>
        <p className="hover-age">{ageSummary(d)}</p>
        {d.kind === 'clade' && <p className="hover-age">{node.leaves().length} families and groups</p>}
        {flag && (
          <p className="hover-flag" style={{ color: flag.color }}>
            {flag.symbol} {flag.label}
          </p>
        )}
        {image && <p className="hover-credit">{photoCredit(image)}</p>}
        <p className="hover-hint">Click to explore</p>
      </div>
    </div>
  )
}
