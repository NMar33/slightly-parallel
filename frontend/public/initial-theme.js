(function () {
  try {
    var saved = localStorage.getItem('sp-theme') || localStorage.getItem('merkhet-theme'); // the second: a browser from before the rename
    var sys = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    var theme = saved === 'dark' || saved === 'light' ? saved : sys;
    document.documentElement.setAttribute('data-theme', theme);
  } catch (_) {
    document.documentElement.setAttribute('data-theme', 'light');
  }
})();
