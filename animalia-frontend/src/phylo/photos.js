// Sized copies of a species photo, so each slot downloads only what it shows.
// iNaturalist serves fixed sizes by file name (small 240px, medium 500px,
// large 1024px); Wikimedia thumbnails carry their width in the path and come
// in standard widths. Photos from any other host are used as stored.

const INATURALIST = /\/(square|small|medium|large|original)\.(jpe?g|png|gif)/i
const WIKIMEDIA_WIDTH = /\/(\d+)px-/
const WIKIMEDIA_SIZES = { small: 250, medium: 500, large: 960 }
// Museum photo services that GBIF links to.
const NATURALIS = /\/format\/(small|medium|large)\b/
const IIIF = /\/full\/(full|max|\d*,\d*)\/0\/default\./
const SMITHSONIAN = /([?&]h=)\d+/
const PIXELS = { small: 250, medium: 500, large: 1000 }

export function photoUrl(image, size = 'medium') {
  if (!image) return null
  const base = size === 'large' ? image.url : image.thumbnail_url || image.url
  if (INATURALIST.test(base)) return base.replace(INATURALIST, (_, _old, ext) => `/${size}.${ext}`)
  if (NATURALIS.test(base)) return base.replace(NATURALIS, `/format/${size}`)
  // IIIF can upscale, so the large size stays the stored copy.
  if (IIIF.test(base)) return size === 'large' ? base : base.replace(IIIF, `/full/${PIXELS[size]},/0/default.`)
  if (SMITHSONIAN.test(base)) return base.replace(SMITHSONIAN, `$1${PIXELS[size]}`)
  const stored = base.match(WIKIMEDIA_WIDTH)
  if (stored) {
    // Never ask for more than the stored copy: larger than the original
    // file, Wikimedia returns the original, which it throttles.
    const wanted = WIKIMEDIA_SIZES[size]
    return wanted < Number(stored[1]) ? base.replace(WIKIMEDIA_WIDTH, `/${wanted}px-`) : base
  }
  return base
}

// A responsive source set for a card photo: 500px on ordinary screens, the
// larger copy on high-density ones.
export function photoSrcSet(image) {
  const medium = photoUrl(image, 'medium')
  const large = photoUrl(image, 'large')
  return medium === large ? undefined : `${medium} 500w, ${large} 1000w`
}
