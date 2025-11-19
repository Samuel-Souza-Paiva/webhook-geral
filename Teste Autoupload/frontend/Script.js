(function(){
  const hostEl = document.querySelector('.host');
  hostEl.textContent = location.origin;

  const MAX = 200;
  const eventos = [];
  const fotos   = [];

  const $ = (s, r=document)=>r.querySelector(s);
  const escapeHtml = s => String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");

  function upsert(arr, rec){ arr.unshift(rec); if(arr.length>MAX) arr.pop(); }

  function renderEventos(items){
    const el = $("#list-eventos"); if(!el) return;
    el.innerHTML = (items || []).map(ev => {
      const pretty = ev?.payload ? JSON.stringify(ev.payload, null, 2) : "";
      const raw = ev?.raw ? String(ev.raw) : "";
      const showRaw = raw && (!pretty || raw.trim() !== pretty.trim());
      return `
        <div class="row">
          <div class="muted">${new Date(ev.ts).toLocaleString()} • IP: ${ev.ip || "-"}</div>
          ${pretty ? `<pre>${escapeHtml(pretty)}</pre>` : `<pre class="muted">{ /* sem JSON parseável */ }</pre>`}
          ${showRaw ? `<details><summary>Raw body</summary><pre>${escapeHtml(raw)}</pre></details>` : ""}
        </div>
      `;
    }).join("");
  }

  function renderFotos(items){
    const el = $("#list-fotos"); if(!el) return;
    el.innerHTML = (items || []).map(ph => `
      <div class="ph">
        <a href="${ph.url}" target="_blank" rel="noreferrer"><img src="${ph.url}" alt="foto"/></a>
        <div class="cap">${new Date(ph.ts).toLocaleString()} • ${ph.ip || ""}<br/>${
          typeof ph.meta === "string" ? ph.meta : ph.meta ? escapeHtml(JSON.stringify(ph.meta)) : ""
        }</div>
      </div>
    `).join("");
  }

  // 1) histórico inicial
  async function loadStatusOnce(){
    try{
      const r = await fetch('/api/status', {cache:'no-store'});
      const j = await r.json();
      (j.eventos||[]).forEach(e=>upsert(eventos, e));
      (j.fotos||[]).forEach(f=>upsert(fotos, f));
      renderEventos(eventos);
      renderFotos(fotos);
    }catch(e){ console.warn('Falha /api/status', e); }
  }

  // 2) tempo real via SSE
  function startSSE(){
    const es = new EventSource('/stream');
    es.onmessage = (ev)=>{
      try{
        const msg = JSON.parse(ev.data);
        if(msg.kind === 'Eventos'){ upsert(eventos, msg.record); renderEventos(eventos); }
        else if(msg.kind === 'FotoEventos'){ upsert(fotos, msg.record); renderFotos(fotos); }
      }catch(_){ /* ignora keepalive/hello */ }
    };
    es.onerror = ()=>{ /* o navegador reconecta automaticamente */ };
  }

  // boot
  loadStatusOnce().then(startSSE);
})();
