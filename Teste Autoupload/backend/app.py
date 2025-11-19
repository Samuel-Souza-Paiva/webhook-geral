# backend/app.py
import asyncio, base64, json, re, mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set, List
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

# ===== Config =====
HOST = "0.0.0.0"   # acessível pelo IP do PC
PORT = 666         # TUDO na porta 666
ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
UPLOAD_DIR   = Path(__file__).resolve().parent / "uploads"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ===== Estado em memória =====
EVENTOS: List[Dict[str, Any]] = []
FOTOS:   List[Dict[str, Any]] = []
CLIENTS: Set[asyncio.Queue] = set()  # assinantes do /stream (SSE)

# ===== Utils =====
def _safe_name(name: Optional[str]) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name or "file")

def _abs_url(request: Request, rel: str) -> str:
    return f"{str(request.base_url).rstrip('/')}{rel}"

def _push(arr: list, item: dict, limit: int = 200) -> None:
    arr.append(item)
    if len(arr) > limit:
        arr.pop(0)

def _broadcast(msg: dict) -> None:
    """Envia 'msg' para todos os clientes conectados ao SSE (/stream)."""
    for q in list(CLIENTS):
        try:
            q.put_nowait(msg)
        except Exception:
            pass

_CT_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/webp": "webp",
}
def _ext_from_content_type(ct: str) -> str:
    ct = (ct or "").split(";")[0].strip().lower()
    if ct in _CT_EXT:
        return _CT_EXT[ct]
    guess = mimetypes.guess_extension(ct) or ""
    if guess.startswith("."):
        return guess[1:]
    return "jpg"

def _save_bytes_to_uploads(data: bytes, ext: str) -> str:
    filename = f"{int(datetime.utcnow().timestamp()*1000)}_foto.{_safe_name(ext or 'jpg')}"
    (UPLOAD_DIR / filename).write_bytes(data)
    return filename

# ===== App =====
app = FastAPI(title="Webhook (porta 666)", version="1.0.0")

# CORS (mesma origem não precisa, mas ajuda em dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Servir arquivos enviados
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR), html=False), name="uploads")

# ===== SSE: stream em tempo real =====
@app.get("/stream")
async def stream(request: Request):
    async def event_gen():
        q: asyncio.Queue = asyncio.Queue()
        CLIENTS.add(q)
        try:
            # hello inicial + keep-alives
            yield f"data: {json.dumps({'kind':'hello','ts': datetime.utcnow().isoformat()+'Z'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(item)}\n\n"
                except asyncio.TimeoutError:
                    # comentário/keepalive para manter conexão
                    yield ": keepalive\n\n"
        finally:
            CLIENTS.discard(q)
    return StreamingResponse(event_gen(), media_type="text/event-stream")

# ===== APIs =====
@app.get("/health")
async def health():
    return {"ok": True, "status": "healthy", "port": PORT}

@app.get("/api/status")
async def api_status():
    return {
        "ok": True,
        "eventos": list(reversed(EVENTOS))[:50],
        "fotos": list(reversed(FOTOS))[:50],
    }

@app.post("/Eventos")
async def post_eventos(request: Request):
    # captura corpo bruto
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8", errors="replace")

    payload: Optional[Dict[str, Any]] = None
    # tenta JSON
    try:
        payload = json.loads(body_text)
    except Exception:
        payload = None
    # tenta x-www-form-urlencoded se não for JSON
    if payload is None:
        qs = parse_qs(body_text, keep_blank_values=True)
        if qs:
            payload = {k: (v[0] if len(v) == 1 else v) for k, v in qs.items()}

    rec = {
        "id": f"{int(datetime.utcnow().timestamp()*1000)}",
        "ts": datetime.utcnow().isoformat()+"Z",
        "ip": request.headers.get("x-forwarded-for") or request.client.host,
        "headers": dict(request.headers),
        "payload": payload,   # quando parseável
        "raw": body_text,     # sempre o corpo bruto
    }
    _push(EVENTOS, rec)
    _broadcast({"kind": "Eventos", "record": rec})
    return {"ok": True, "id": rec["id"]}

@app.post("/FotoEventos")
async def post_foto_eventos(
    request: Request,
    # parâmetros “nomeados” comuns (mas vamos tolerar outros via request.form())
    foto: Optional[UploadFile] = File(default=None),
    fotoBase64: Optional[str]   = Form(default=None),
    meta: Optional[str]         = Form(default=None),
):
    """
    Aceita:
      1) multipart/form-data com QUALQUER nome de campo de arquivo (foto, file, image, snapshot, pic…)
      2) JSON com fotoBase64 / imageBase64 / image / data (data-URL ou base64 puro)
      3) x-www-form-urlencoded com as chaves acima
      4) Corpo cru (application/octet-stream ou image/*) contendo bytes da imagem
      5) Base64 “solto” no corpo (sem JSON)
    """
    ct = (request.headers.get("content-type") or "").lower()
    ip = request.headers.get("x-forwarded-for") or request.client.host

    # ---------- CASO A: multipart/form-data ----------
    if "multipart/form-data" in ct:
        form = await request.form()
        # 1) tente pegar qualquer UploadFile por nomes comuns
        file_obj: Optional[UploadFile] = None
        for key in ("foto", "file", "image", "snapshot", "pic", "upload", "photo", "picture"):
            val = form.get(key)
            if isinstance(val, UploadFile):
                file_obj = val
                break
        # 2) se não achou, pegue o primeiro UploadFile que aparecer
        if file_obj is None:
            for _, val in form.multi_items():
                if isinstance(val, UploadFile):
                    file_obj = val
                    break
        # 3) meta (pode vir com outros nomes)
        meta = meta or form.get("meta") or form.get("data") or form.get("json")

        if file_obj is not None:
            data = await file_obj.read()
            if not data:
                raise HTTPException(status_code=400, detail="Arquivo vazio")
            # derive ext do content-type do arquivo, se houver
            ext = _ext_from_content_type(getattr(file_obj, "content_type", "") or "")
            filename = _save_bytes_to_uploads(data, ext)
            via = "multipart"
        else:
            # talvez veio base64 dentro do multipart
            fb64 = fotoBase64 or form.get("fotoBase64") or form.get("imageBase64") or form.get("image") or form.get("data")
            if not fb64:
                raise HTTPException(status_code=400, detail="Nenhum arquivo encontrado nem base64 fornecido")
            b64 = str(fb64).strip()
            if b64.startswith("data:"):
                try:
                    header, b64data = b64.split(",", 1)
                    mime = header.split(";")[0].split(":")[1]
                    ext = (mime.split("/")[1] or "jpg").lower()
                except Exception:
                    b64data, ext = b64, "jpg"
            else:
                b64data, ext = b64, "jpg"
            try:
                raw = base64.b64decode(b64data, validate=True)
            except Exception:
                raise HTTPException(status_code=400, detail="Base64 inválido (multipart)")
            filename = _save_bytes_to_uploads(raw, ext)
            via = "base64-multipart"

    # ---------- CASO B: JSON ----------
    elif "application/json" in ct:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="JSON inválido")
        # aceita várias chaves possíveis
        fb64 = (
            (body.get("fotoBase64") if isinstance(body, dict) else None)
            or (body.get("imageBase64") if isinstance(body, dict) else None)
            or (body.get("image") if isinstance(body, dict) else None)
            or (body.get("data") if isinstance(body, dict) else None)
        )
        meta = body.get("meta") if isinstance(body, dict) else None
        if not fb64:
            raise HTTPException(status_code=400, detail="JSON sem campo base64 (fotoBase64/imageBase64/image/data)")
        b64 = str(fb64).strip()
        if b64.startswith("data:"):
            try:
                header, b64data = b64.split(",", 1)
                mime = header.split(";")[0].split(":")[1]
                ext = (mime.split("/")[1] or "jpg").lower()
            except Exception:
                b64data, ext = b64, "jpg"
        else:
            b64data, ext = b64, "jpg"
        try:
            raw = base64.b64decode(b64data, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Base64 inválido (JSON)")
        filename = _save_bytes_to_uploads(raw, ext)
        via = "base64-json"

    # ---------- CASO C: x-www-form-urlencoded ----------
    elif "application/x-www-form-urlencoded" in ct:
        body_text = (await request.body()).decode("utf-8", errors="replace")
        qs = parse_qs(body_text, keep_blank_values=True)
        fb64 = (
            qs.get("fotoBase64", [None])[0]
            or qs.get("imageBase64", [None])[0]
            or qs.get("image", [None])[0]
            or qs.get("data", [None])[0]
        )
        meta = meta or qs.get("meta", [None])[0]
        if not fb64:
            raise HTTPException(status_code=400, detail="Form-urlencoded sem base64 (fotoBase64/imageBase64/image/data)")
        b64 = str(fb64).strip()
        if b64.startswith("data:"):
            try:
                header, b64data = b64.split(",", 1)
                mime = header.split(";")[0].split(":")[1]
                ext = (mime.split("/")[1] or "jpg").lower()
            except Exception:
                b64data, ext = b64, "jpg"
        else:
            b64data, ext = b64, "jpg"
        try:
            raw = base64.b64decode(b64data, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="Base64 inválido (form)")
        filename = _save_bytes_to_uploads(raw, ext)
        via = "base64-form"

    # ---------- CASO D: binário cru (image/* ou octet-stream) ----------
    elif ct.startswith("image/") or "application/octet-stream" in ct:
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=400, detail="Corpo vazio (imagem crua)")
        ext = _ext_from_content_type(ct)
        filename = _save_bytes_to_uploads(raw, ext)
        via = "binary"

    # ---------- CASO E: tentar detectar base64 solto ----------
    else:
        body_text = (await request.body()).decode("utf-8", errors="replace").strip()
        if body_text:
            b64 = body_text
            if b64.startswith("data:"):
                try:
                    header, b64data = b64.split(",", 1)
                    mime = header.split(";")[0].split(":")[1]
                    ext = (mime.split("/")[1] or "jpg").lower()
                except Exception:
                    b64data, ext = b64, "jpg"
            else:
                b64data, ext = b64, "jpg"
            try:
                raw = base64.b64decode(b64data, validate=True)
            except Exception:
                raise HTTPException(status_code=400, detail="Formato não suportado: envie multipart, JSON, form, imagem crua ou base64")
            filename = _save_bytes_to_uploads(raw, ext)
            via = "base64-raw"
        else:
            raise HTTPException(status_code=400, detail="Requisição sem corpo")

    # monta registro e emite SSE
    rec = {
        "id": f"{int(datetime.utcnow().timestamp()*1000)}",
        "ts": datetime.utcnow().isoformat()+"Z",
        "ip": ip,
        "filename": filename,
        "url": f"/uploads/{filename}",
        "meta": meta,
        "via": via,
    }
    _push(FOTOS, rec)
    _broadcast({"kind": "FotoEventos", "record": rec})
    return {"ok": True, "id": rec["id"], "url": _abs_url(request, rec["url"]), "via": via}

# Monta o frontend NA RAIZ — abre index.html e assets
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

# Execução diretahttp://10.100.68.99:666/
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, reload=False)
