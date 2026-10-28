/* Deep links reveal only the selected recorded task or node. Native disclosures work without JS. */
(() => {
  const reveal = () => {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    if (!/^obs-(?:case-(?:delivery|internet|once|speed)|node-(?:A|B|R1))$/.test(id)) return;
    const target = document.getElementById(id);
    if (target instanceof HTMLDetailsElement) target.open = true;
  };
  addEventListener('hashchange', reveal);
  reveal();
})();
