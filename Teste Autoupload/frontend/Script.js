(function(){

  const hostEl = document.querySelector('.host');
  if (hostEl) hostEl.textContent = location.origin;

  const MAX = 200;
  const eventos = [];
  const fotos = [];

  const listEventos = document.getElementById("list-eventos");
  const listFotos   = document.getElementById("list-fotos");

  function upsert(arr, rec){
    arr.unshift(rec);
    if (arr.length > MAX) arr.pop();
  }

  function escapeHtml(s){
    return String(s)
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;");
  }

  // RENDERIZAÇÃO DOS EVENTOS
  function renderEventos(items){     // ⬅
    if (!listEventos) return;

    listEventos.innerHTML = items.map(ev => {
      const pretty = ev?.payload ? JSON.stringify(ev.payload, null, 2) : "";
      return `
        <div class="row">
          <div class="muted">${new Date(ev.ts).toLocaleString()} • IP: ${ev.ip || "-"}</div>
          <pre>${escapeHtml(pretty)}</pre>
        </div>
      `;
    }).join("");
  }

  // RENDERIZAÇÃO DAS FOTOS
  function renderFotos(items){       // 
    if (!listFotos) return;

    listFotos.innerHTML = items.map(ph => {
      const url = `${ph.url}?t=${Date.now()}`;
      return `
        <div class="ph">
          <img src="${url}" loading="lazy" />
          <div class="cap">${new Date(ph.ts).toLocaleString()}</div>
        </div>
      `;
    }).join("");
  }

  // HISTÓRICO INICIAL
  async function loadStatusOnce(){
    try{
      const r = await fetch('/api/status', { cache:'no-store' });
      const j = await r.json();

      (j.eventos || []).forEach(e => upsert(eventos, e));
      (j.fotos   || []).forEach(f => upsert(fotos, f));

      renderEventos(eventos);
      renderFotos(fotos);

    } catch(e){
      console.error("Erro em /api/status:", e);
    }
  }

  // SSE EM TEMPO REAL
  function startSSE(){
    const es = new EventSource('/stream');

    es.onmessage = ev => {
      try {
        const msg = JSON.parse(ev.data);

        if (msg.kind === "Eventos") {
          upsert(eventos, msg.record);
          renderEventos(eventos);

        } else if (msg.kind === "FotoEventos") {
          upsert(fotos, msg.record);
          renderFotos(fotos);
        }

      } catch(e){
        // Keepalive / hello
      }
    };
  }

  // BOOT
  loadStatusOnce().then(startSSE);

})();
