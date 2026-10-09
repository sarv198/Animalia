import { formatAge } from '../phylogenyLayout.js'

export function displayName(data) {
  if (data.name) return data.extinct ? `† ${data.name}` : data.name
  return 'Unnamed common ancestor'
}

export function ageRange(data) {
  if (data.age_ci_low == null || data.age_ci_high == null) return null
  return `${formatAge(data.age_ci_low)} to ${formatAge(data.age_ci_high)}`
}

// One-line age summary, as shown in the hover card.
export function ageSummary(data) {
  if (data.kind === 'clade') {
    const range = ageRange(data)
    return `Split ~${formatAge(data.age_ma)} million years ago${range ? ` (${range})` : ''}`
  }
  if (data.kind === 'group' && data.extinct) {
    return `Fossils from ${formatAge(data.first_appearance_ma)} to ${formatAge(data.last_appearance_ma)} million years ago`
  }
  return `Split from its relatives ~${formatAge(data.stem_age_ma)} million years ago`
}

// Credit line for a photo, required by its licence.
export function photoCredit(image) {
  return `Photo: ${image.creator || 'unknown'} · ${image.licence} · via ${image.source}`
}

// Where a date comes from: "Date: TimeTree 5, 17 studies. Kumar et al. 2022, ..."
export function dateSource(data) {
  if (!data.age_source) return ''
  const studies = data.age_study_count ? `, ${data.age_study_count} studies` : ''
  const citation = data.age_citation ? ` ${data.age_citation}` : ''
  return `Date: ${data.age_source}${studies}.${citation}`
}
