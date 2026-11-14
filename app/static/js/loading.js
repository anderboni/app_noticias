(function () {
  const bar = document.getElementById("loading-bar");
  if (!bar) return;

  function showLoading() {
    document.body.classList.add("is-loading");
    bar.classList.add("is-active");
    bar.setAttribute("aria-hidden", "false");
  }

  function hideLoading() {
    document.body.classList.remove("is-loading");
    bar.classList.remove("is-active");
    bar.setAttribute("aria-hidden", "true");
  }

  window.AppLoading = { show: showLoading, hide: hideLoading };

  // Ao enviar formulários (ex.: coletar notícias)
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      showLoading();
    });
  });

  // Ao sair/recarregar a página
  window.addEventListener("beforeunload", function () {
    showLoading();
  });

  // Garante que a barra some quando a página termina de carregar
  window.addEventListener("pageshow", function () {
    hideLoading();
  });
  hideLoading();

  const minutes = parseFloat(document.body.dataset.refreshMinutes || "0", 10);
  if (minutes > 0 && !Number.isNaN(minutes)) {
    const ms = minutes * 60 * 1000;
    setTimeout(function () {
      showLoading();
      window.location.reload();
    }, ms);
  }
})();
