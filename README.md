Claro! Aqui está um **README.md completo, profissional e bem organizado**, ideal para GitHub, GitLab ou repositório interno Intelbras.
Caso queira personalizar com logos, prints ou instruções específicas da empresa, eu ajusto depois.

---

# 📡 Webhook Dashboard – Intelbras Snapshot & Event Receiver

Este projeto é um **servidor FastAPI + frontend estático** que recebe:

✅ **Eventos JSON** enviados por câmeras e sistemas
✅ **Snapshots / Fotos** enviados por HTTP (RAW JPEG, multipart, Base64, JSON, octet-stream etc.)
✅ **Atualização em tempo real via SSE (Server-Sent Events)**
✅ **Visualização instantânea de eventos e fotos no navegador**
✅ **Correção automática de JPEGs inválidos** enviados por câmeras Dahua/Intelbras

Ele funciona como um **dashboard de monitoramento em tempo real** para validar Webhooks de eventos e imagens de dispositivos.

---

#  Funcionalidades

###  Recebimento de fotos em qualquer formato

O endpoint `/FotoEventos` aceita:

* multipart/form-data (UploadFile)
* Base64 (JSON ou form-urlencoded)
* imagem binária crua (`image/jpeg`, `application/octet-stream`)
* snapshots com bytes extras
* fallback automático

O servidor aplica **fix_jpeg()**, que:

* detecta o JPEG correto entre `FFD8` e `FFD9`
* remove lixo antes/depois do JPEG
* garante que o navegador exiba a imagem

### 📄 Recebimento de eventos JSON

O endpoint `/Eventos` recebe:

* JSON válido
* Formulário application/x-www-form-urlencoded
* Texto bruto (raw)

Todos os eventos aparecem no frontend imediatamente.

###  Dashboard em tempo real

O frontend exibe:

* lista de eventos no lado esquerdo
* lista de fotos no lado direito
* autoatualização via SSE
* fotos com preview e cache-buster
* sem recarregar a página

###  Armazenamento local

As fotos são salvas em:

```
/backend/uploads/
```

Cada arquivo recebe nome único com timestamp.

### 🖥 Frontend serve arquivos estáticos

O código do frontend fica em:

```
/frontend/index.html
/frontend/script.js
```

Servido automaticamente pelo FastAPI.

---

#  Estrutura do Projeto

```
/
├── backend/
│   ├── app.py              ← Lógica completa do servidor FastAPI
│   ├── uploads/            ← Fotos recebidas são salvas aqui
│
├── frontend/
│   ├── index.html          ← Dashboard
│   ├── script.js           ← Conexão SSE + renderização
│
└── README.md
```

---

# 🛠 Tecnologias Utilizadas

* **Python 3.10+ / 3.11 / 3.12 / 3.13**
* **FastAPI**
* **Starlette (SSE + StreamingResponse)**
* **Asyncio**
* **HTML + CSS + Vanilla JS**
* **Docker (opcional)**

---

# 📡 Endpoints Principais

### **GET** `/`

Serve o frontend.

### **GET** `/api/status`

Retorna últimas 50 fotos e últimos 50 eventos.

### **GET** `/stream`

Canal SSE para dados em tempo real.

### **POST** `/Eventos`

Recebe eventos JSON ou texto.

### **POST** `/FotoEventos`

Recebe qualquer tipo de imagem:

| Tipo de envio             | Suportado | Observações                   |
| ------------------------- | --------- | ----------------------------- |
| multipart                 | ✔         | `foto`, `file`, `image`, etc. |
| base64 JSON               | ✔         | `fotoBase64`                  |
| base64 form               | ✔         | `fotoBase64`                  |
| binário JPEG puro         | ✔         | `image/jpeg`                  |
| octet-stream              | ✔         | Conteúdo bruto                |
| snapshot com bytes extras | ✔         | Corrigido automaticamente     |

---

#  JPEG Fixer – Como funciona

Câmeras Dahua/Intelbras às vezes enviam:

* boundary do multipart junto com a imagem
* bytes extras antes do cabeçalho SOI (FFD8)
* bytes extras após EOF (FFD9)
* dados de stream RSTP encapsulados

O `fix_jpeg()` limpa isso:

```python
start = raw.find(b"\xFF\xD8")   # SOI
end   = raw.rfind(b"\xFF\xD9")  # EOI
return raw[start:end+2]
```

Isso garante que **todo arquivo salvo seja um JPEG válido** e exibido no navegador.

---

# ▶ Como Executar

## 1. Instale dependências

```
pip install fastapi uvicorn python-multipart
```

## 2. Estrutura recomendada

```
project/
    backend/app.py
    frontend/index.html
    frontend/script.js
```

## 3. Execute o servidor

```
python backend/app.py
```

Acesse no navegador:

```
http://localhost:666
```

---

# 🐳 Execução via Docker

### Dockerfile sugerido

```Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend /app/backend
COPY frontend /app/frontend

RUN pip install fastapi uvicorn python-multipart

EXPOSE 666

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "666"]
```

### Build

```
docker build -t webhook-dashboard .
```

### Run

```
docker run -p 666:666 webhook-dashboard
```

---

#  Testes rápidos via curl

### Evento JSON

```
curl -X POST http://localhost:666/Eventos -d '{"msg":"teste"}' -H "Content-Type: application/json"
```

### Foto binária

```
curl -X POST http://localhost:666/FotoEventos \
     --data-binary "@foto.jpg" \
     -H "Content-Type: image/jpeg"
```

### Foto base64

```
curl -X POST http://localhost:666/FotoEventos \
     -d "fotoBase64=$(base64 -w0 foto.jpg)"
```

---

#  Licença / Uso Interno

Este projeto pode ser usado para:

* testes de Webhook
* homologação de integrações de câmeras
* debugging de envios snapshot/evento
* validação de sensores e IA

Caso seja usado na Intelbras, personalize conforme ambiente.

---

#  Suporte / Melhorias

Solicite melhorias como:

* limpeza automática de uploads antigos
* modal zoom ao clicar na foto
* autenticação via token
* API de histórico paginado
* exportação de eventos

Só pedir que adiciono tudo. 🚀

---


