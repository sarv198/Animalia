// Families that Open Tree's taxonomy does not hold as a family with species:
// the family follows The Reptile Database (its species are still placed by
// Open Tree's tree). The wording comes from opentree_family in the data.
export const OPENTREE_STANDING = {
  empty: "Open Tree's taxonomy lists the name but files no species under it.",
  unranked: "Open Tree's taxonomy does not rank it as a family.",
  missing: "Open Tree's taxonomy does not list this family yet.",
}

export function isReptileDatabaseFamily(data) {
  return data?.kind === 'family' && Boolean(OPENTREE_STANDING[data.opentree_family])
}
