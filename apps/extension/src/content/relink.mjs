// An SPA can re-render its whole form while fillForm waits for /map-fields
// (Greenhouse's embedded board does, live): the held elements are then detached
// and writes to them go nowhere. relink finds each old control's live twin.
// sig = {tag, type, id, name}. Returns, per old control, its fresh index or -1.
const same = (a, b) => a.tag === b.tag && a.type === b.type && a.id === b.id && a.name === b.name;

export function relink(oldSigs, freshSigs) {
  return oldSigs.map((o, i) => {
    if (oldSigs.length === freshSigs.length && same(o, freshSigs[i])) return i;
    return o.id ? freshSigs.findIndex((f) => f.id === o.id && same(o, f)) : -1;
  });
}
