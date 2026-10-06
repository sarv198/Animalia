import { formatAge } from '../phylogenyLayout.js'
import { majorClade } from '../phylogenyStyle.js'
import { displayName } from './labels.js'

export default function FamilyTable({ model, selectedId, onSelect }) {
  return (
    <div className="phylo-table-wrap">
      <table className="phylo-table">
        <thead>
          <tr>
            <th scope="col">Family or group</th>
            <th scope="col">Major clade</th>
            <th scope="col">Representative species</th>
            <th scope="col">Split from relatives (Ma)</th>
            <th scope="col">Placement</th>
          </tr>
        </thead>
        <tbody>
          {model.leaves.map((leaf) => {
            const d = leaf.data
            const clade = majorClade(leaf)
            return (
              <tr
                key={d.id}
                className={d.id === selectedId ? 'selected' : undefined}
                onClick={() => onSelect(d.id)}
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelect(d.id)
                  }
                }}
              >
                <th scope="row">{displayName(d)}</th>
                <td>
                  <span className="swatch" style={{ background: clade.color }} aria-hidden="true" />
                  {clade.name || 'Other'}
                </td>
                <td><em>{d.representative_species?.scientific_name || '—'}</em></td>
                <td className="num">{formatAge(d.stem_age_ma)}</td>
                <td>{d.kind === 'family' ? d.placement_status : d.extinct ? 'extinct group' : 'living group'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
