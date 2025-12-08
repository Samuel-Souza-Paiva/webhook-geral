import asyncio, base64, json, re, mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set, List
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse


# ===========================================================
# CONFIG
# ===========================================================
HOST = "0.0.0.0"
PORT = 666

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
UPLOAD_DIR   = Path(__file__).resolve().parent / "uploads"

FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ===========================================================
# MEMÓRIA EM TEMPO DE EXECUÇÃO
# ===========================================================
EVENTOS: List[Dict[str, Any]] = []
FOTOS:   List[Dict[str, Any]] = []
CLIENTS: Set[asyncio.Queue] = set()


# ===========================================================
# UTILS
# ===========================================================
def _safe_name(name: Optional[str]) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name or "file")

def _abs_url(request: Request, rel: str) -> str:
    return f"{str(request.base_url).rstrip('/')}{rel}"

def _push(arr: list, item: dict, limit: int = 200) -> None:
    arr.append(item)
    if len(arr) > limit:
        arr.pop(0)

def _broadcast(msg: dict) -> None:
    for q in list(CLIENTS):
        try:
            q.put_nowait(msg)
        except:
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


# ===========================================================
# FIX JPEG — remove bytes estranhos antes/depois do JPEG real
# ===========================================================
def fix_jpeg(raw: bytes) -> bytes:
    """
    A maioria das câmeras envia snapshots brutos com bytes extras.
    Aqui extraímos apenas o conteúdo JPEG válido entre FFD8 e FFD9.
    """
    start = raw.find(b"\xFF\xD8")   # SOI
    end   = raw.rfind(b"\xFF\xD9")  # EOI

    if start != -1 and end != -1 and end > start:
        return raw[start:end+2]

    return raw  # fallback: sem mudanças


def _save_bytes_to_uploads(data: bytes, ext: str) -> str:
    filename = f"{int(datetime.utcnow().timestamp()*1000)}_foto.{_safe_name(ext or 'jpg')}"
    (UPLOAD_DIR / filename).write_bytes(data)
    return filename


def _decode_and_save_base64(b64str: str):
    s = str(b64str).strip()

    if s.startswith("data:"):
        header, b64data = s.split(",", 1)
        mime = header.split(";")[0].split(":")[1]
        ext = mime.split("/")[1]
    else:
        b64data = s
        ext = "jpg"

    raw = base64.b64decode(b64data, validate=True)
    raw = fix_jpeg(raw)
    filename = _save_bytes_to_uploads(raw, ext)
    return filename, "base64"



# ===========================================================
# FASTAPI APP
# ===========================================================
app = FastAPI(title="Webhook Intelbras", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


# ===========================================================
# SSE /stream
# ===========================================================
@app.get("/stream")
async def stream(request: Request):
    async def event_gen():
        q: asyncio.Queue = asyncio.Queue()
        CLIENTS.add(q)

        yield f"data: {json.dumps({'kind':'hello','ts': datetime.utcnow().isoformat()+'Z'})}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(item)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            CLIENTS.discard(q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")



# ===========================================================
# STATUS
# ===========================================================
@app.get("/health")
def health():
    return {"ok": True, "status": "healthy", "port": PORT}


@app.get("/api/status")
def api_status():
    return {
        "ok": True,
        "eventos": list(reversed(EVENTOS))[:50],
        "fotos":   list(reversed(FOTOS))[:50],
    }



# ===========================================================
# /Eventos
# ===========================================================
@app.post("/Eventos")
async def post_eventos(request: Request):
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8", errors="replace")

    payload = None
    try:
        payload = json.loads(body_text)
    except:
        qs = parse_qs(body_text, keep_blank_values=True)
        if qs:
            payload = {k: v[0] if len(v)==1 else v for k,v in qs.items()}

    rec = {
        "id": f"{int(datetime.utcnow().timestamp()*1000)}",
        "ts": datetime.utcnow().isoformat()+"Z",
        "ip": request.headers.get("x-forwarded-for") or request.client.host,
        "headers": dict(request.headers),
        "payload": payload,
        "raw": body_text,
    }

    _push(EVENTOS, rec)
    _broadcast({"kind": "Eventos", "record": rec})
    return {"ok": True}



# ===========================================================
# /FotoEventos
# ===========================================================
@app.post("/FotoEventos")
async def post_foto_eventos(
    request: Request,
    foto: Optional[UploadFile] = File(default=None),
    fotoBase64: Optional[str] = Form(default=None),
    meta: Optional[str]       = Form(default=None),
):

    ct = (request.headers.get("content-type") or "").lower()
    ip = request.headers.get("x-forwarded-for") or request.client.host

    # -------------------------------------------------------
    # A) MULTIPART
    # -------------------------------------------------------
    if "multipart/form-data" in ct:
        form = await request.form()

        file_obj = None
        for key in ("foto","file","image","snapshot","pic","upload"):
            v = form.get(key)
            if isinstance(v, UploadFile):
                file_obj = v
                break

        if not file_obj:
            for _, v in form.multi_items():
                if isinstance(v, UploadFile):
                    file_obj = v
                    break

        meta = meta or form.get("meta") or form.get("data") or form.get("json")

        if file_obj:
            raw = await file_obj.read()
            raw = fix_jpeg(raw)
            ext = _ext_from_content_type(file_obj.content_type or "")
            filename = _save_bytes_to_uploads(raw, ext)
            via = "multipart"

        else:
            fb64 = fotoBase64 or form.get("fotoBase64") or form.get("imageBase64") or form.get("data")
            filename, via = _decode_and_save_base64(fb64)


    # -------------------------------------------------------
    # B) JSON BASE64
    # -------------------------------------------------------
    elif "application/json" in ct:
        body = await request.json()
        fb64 = body.get("fotoBase64") or body.get("imageBase64") or body.get("image") or body.get("data")
        meta = body.get("meta")
        filename, via = _decode_and_save_base64(fb64)


    # -------------------------------------------------------
    # C) FORM-URLENCODED
    # -------------------------------------------------------
    elif "application/x-www-form-urlencoded" in ct:
        body_text = (await request.body()).decode("utf-8","replace")
        qs = parse_qs(body_text)
        fb64 = qs.get("fotoBase64",[None])[0] or qs.get("image",[None])[0]
        filename, via = _decode_and_save_base64(fb64)


    # -------------------------------------------------------
    # D) IMAGEM BINÁRIA
    # -------------------------------------------------------
    elif ct.startswith("image/") or "application/octet-stream" in ct:
        raw = await request.body()
        raw = fix_jpeg(raw)
        ext = _ext_from_content_type(ct)
        filename = _save_bytes_to_uploads(raw, ext)
        via = "binary"


    # -------------------------------------------------------
    # E) FALLBACK — JPEG puro sem header
    # -------------------------------------------------------
    else:
        body = await request.body()
        try:
            text = body.decode("utf-8","ignore").strip()
            filename, via = _decode_and_save_base64(text)
        except:
            raw = fix_jpeg(body)
            filename = _save_bytes_to_uploads(raw, "jpg")
            via = "raw-binary-fallback"


    # Registro final
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
    return {"ok": True, "url": f"/uploads/{filename}", "via": via}



# ===========================================================
# STATIC FILES (ordem importa)
# ===========================================================
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR), html=False), name="uploads")
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")



# ===========================================================
# MAIN
# ===========================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, reload=False)
