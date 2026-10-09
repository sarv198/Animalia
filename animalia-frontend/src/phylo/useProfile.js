import { useEffect, useState } from 'react'
import { fetchProfile } from '../api.js'

// Profiles never change while the page is open, so each is fetched once.
const cache = new Map()

// The profile (Wikipedia summary, species count, range map) of a named node.
export function useProfile(name) {
  const [failed, setFailed] = useState(null)
  const [, setLoaded] = useState(0)

  useEffect(() => {
    if (!name || cache.has(name)) return undefined
    let cancelled = false
    fetchProfile(name)
      .then((profile) => {
        cache.set(name, profile)
        if (!cancelled) setLoaded((n) => n + 1)
      })
      .catch(() => {
        if (!cancelled) setFailed(name)
      })
    return () => {
      cancelled = true
    }
  }, [name])

  if (!name) return { profile: null, state: 'none' }
  if (cache.has(name)) return { profile: cache.get(name), state: 'ready' }
  return { profile: null, state: failed === name ? 'error' : 'loading' }
}
