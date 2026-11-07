// A crop name turned into the handle a guide page is addressed by.
//
// Mirrors `slugify` in backend/crops.py, because both sides have to agree on
// what "Dry beans" becomes: lowercase, runs of anything that is not a letter or
// digit collapse to one dash, and no leading or trailing dash. The backend
// resolves the result against scientific names first, then curated common names,
// then South African local names, so a name typed into "My plants" reaches the
// same page a recommendation card does.

export function slugify(text) {
  return String(text || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}
