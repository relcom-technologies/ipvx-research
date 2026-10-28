/* Only explicit language links choose a language; never silently redirect readers. */
(() => {
  for (const link of document.querySelectorAll('.language-switch a')) {
    link.addEventListener('click', () => {
      const url = new URL(link.href, location.href);
      if (url.origin === location.origin) {
        url.hash = location.hash;
        link.href = url.href;
      }
    });
  }
})();
