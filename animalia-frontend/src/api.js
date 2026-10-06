export const API_BASE_URL = 'http://127.0.0.1:8001'

async function getJson(path) {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export function fetchTree() {
  return getJson('/api/tree/reptiles')
}

export function fetchPhylogeny() {
  return getJson('/api/phylogeny/reptiles')
}

export function fetchSources() {
  return getJson('/api/phylogeny/sources')
}

export function fetchSpecies(id) {
  return getJson(`/api/species/${id}`)
}
