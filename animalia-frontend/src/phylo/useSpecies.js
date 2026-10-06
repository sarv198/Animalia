import { useEffect, useState } from 'react'
import { fetchSpecies } from '../api.js'

// Load one species' details (photos, IUCN status, links) by id.
export function useSpecies(speciesId) {
  const [species, setSpecies] = useState(null)
  const [state, setState] = useState('loading')

  useEffect(() => {
    if (speciesId == null) return undefined
    let cancelled = false
    fetchSpecies(speciesId)
      .then((data) => {
        if (cancelled) return
        setSpecies(data)
        setState('ready')
      })
      .catch(() => {
        if (!cancelled) setState('error')
      })
    return () => {
      cancelled = true
    }
  }, [speciesId])

  return { species, state }
}

// The animal leads: its photo, then its names.
