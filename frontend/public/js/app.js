/**
 * Satellite Image Compositor — Frontend JS
 * Suporta MÚLTIPLAS áreas de interesse (AOIs).
 * Cada AOI gera um job separado ao processar.
 */

// ═══════════════════════════════════════════════════════
// ESTADO GLOBAL
// ═══════════════════════════════════════════════════════

/** @type {Array<{id: string, name: string, geojson: object, layer: L.Layer}>} */
let aoiList = [];
let aoiCounter = 0;           // auto-incremento para IDs
let selectedAoiId = null;     // AOI selecionada no painel
let pollingIntervals = {};    // job_id -> intervalId

// Cores para diferenciar AOIs no mapa
const AOI_COLORS = [
    "#4f8cff", "#ff6b6b", "#51cf66", "#fcc419",
    "#cc5de8", "#ff922b", "#22b8cf", "#ff78a7",
    "#20c997", "#a9e34b", "#748ffc", "#e599f7",
];

function getAoiColor(index) {
    return AOI_COLORS[index % AOI_COLORS.length];
}

// ═══════════════════════════════════════════════════════
// MAPA LEAFLET
// ═══════════════════════════════════════════════════════
const map = L.map("map").setView([-22.75, -47.25], 9);

L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
    maxZoom: 19,
}).addTo(map);

// Layer group para todas as AOIs
const aoiLayerGroup = new L.FeatureGroup();
map.addLayer(aoiLayerGroup);

// Leaflet Draw (desenha novas AOIs)
const drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

const drawControl = new L.Control.Draw({
    draw: {
        polygon: {
            allowIntersection: false,
            shapeOptions: { color: "#4f8cff", weight: 2, fillOpacity: 0.15 },
        },
        rectangle: {
            shapeOptions: { color: "#4f8cff", weight: 2, fillOpacity: 0.15 },
        },
        circle: false,
        circlemarker: false,
        marker: false,
        polyline: false,
    },
    edit: false, // edição é feita via lista, não pelo draw control
});
map.addControl(drawControl);

// Evento: polígono desenhado → adiciona como nova AOI
map.on(L.Draw.Event.CREATED, (e) => {
    const geojson = e.layer.toGeoJSON().geometry;
    const name = `Área ${aoiCounter + 1}`;
    addAoi(name, geojson);
});

// ═══════════════════════════════════════════════════════
// AOI — MULTI
// ═══════════════════════════════════════════════════════

/**
 * Adiciona uma nova AOI à lista.
 * @param {string} name - Nome da AOI
 * @param {object} geojson - GeoJSON geometry (Polygon/MultiPolygon)
 */
function addAoi(name, geojson) {
    aoiCounter++;
    const id = `aoi_${aoiCounter}`;
    const color = getAoiColor(aoiList.length);

    // Cria layer no mapa
    const layer = L.geoJSON(geojson, {
        style: { color: color, weight: 2, fillOpacity: 0.12, fillColor: color },
    });

    // Tooltip com nome
    layer.bindTooltip(name, {
        permanent: true,
        direction: "center",
        className: "aoi-tooltip",
    });

    // Click na layer → seleciona
    layer.on("click", () => selectAoi(id));

    // Adiciona ao grupo
    aoiLayerGroup.addLayer(layer);

    // Adiciona ao estado
    aoiList.push({ id, name, geojson, layer, color });

    // Seleciona automaticamente
    selectAoi(id);

    // Zoom para a nova AOI
    map.fitBounds(layer.getBounds(), { padding: [50, 50] });

    toast(`AOI "${name}" adicionada!`, "success");
    renderAoiList();
    updateAoiCount();
}

/**
 * Remove uma AOI por ID.
 */
function removeAoi(id) {
    const idx = aoiList.findIndex((a) => a.id === id);
    if (idx === -1) return;

    const aoi = aoiList[idx];
    aoiLayerGroup.removeLayer(aoi.layer);
    aoiList.splice(idx, 1);

    if (selectedAoiId === id) {
        selectedAoiId = null;
        document.getElementById("aoiPreview").value = "";
    }

    toast(`AOI "${aoi.name}" removida.`, "info");
    renderAoiList();
    updateAoiCount();
}

/**
 * Seleciona uma AOI (destaca no mapa e mostra GeoJSON).
 */
function selectAoi(id) {
    selectedAoiId = id;
    const aoi = aoiList.find((a) => a.id === id);
    if (!aoi) return;

    // Mostra GeoJSON no preview
    document.getElementById("aoiPreview").value = JSON.stringify(aoi.geojson, null, 2);

    // Destaque visual: aumenta opacidade da selecionada, diminui das outras
    aoiList.forEach((a) => {
        const isSelected = a.id === id;
        a.layer.setStyle({
            weight: isSelected ? 3 : 2,
            fillOpacity: isSelected ? 0.25 : 0.08,
            opacity: isSelected ? 1 : 0.5,
        });
    });

    // Zoom para a AOI selecionada
    map.fitBounds(aoi.layer.getBounds(), { padding: [50, 50] });

    renderAoiList();
}

/**
 * Remove todas as AOIs.
 */
function clearAllAois() {
    aoiLayerGroup.clearLayers();
    aoiList = [];
    selectedAoiId = null;
    document.getElementById("aoiPreview").value = "";
    renderAoiList();
    updateAoiCount();
    toast("Todas as AOIs removidas.", "info");
}

/**
 * Zoom para todas as AOIs.
 */
function fitAllAois() {
    if (aoiList.length === 0) {
        toast("Nenhuma AOI adicionada.", "error");
        return;
    }
    map.fitBounds(aoiLayerGroup.getBounds(), { padding: [50, 50] });
}

/**
 * Renderiza a lista de AOIs na sidebar.
 */
function renderAoiList() {
    const container = document.getElementById("aoiList");

    if (aoiList.length === 0) {
        container.innerHTML = '<p style="font-size:12px;color:var(--text-muted)">Nenhuma AOI adicionada.</p>';
        return;
    }

    container.innerHTML = aoiList
        .map((aoi) => {
            const isSelected = aoi.id === selectedAoiId;
            return `
            <div class="aoi-item ${isSelected ? "selected" : ""}" onclick="selectAoi('${aoi.id}')">
                <span class="aoi-color-dot" style="background:${aoi.color}"></span>
                <span class="aoi-name">${aoi.name}</span>
                <button class="aoi-remove-btn" onclick="event.stopPropagation(); removeAoi('${aoi.id}')" title="Remover">✕</button>
            </div>
        `;
        })
        .join("");
}

function updateAoiCount() {
    const el = document.getElementById("aoiCount");
    const n = aoiList.length;
    el.textContent = n === 0
        ? "Nenhuma AOI selecionada"
        : `${n} AOI${n > 1 ? "s" : ""} → ${n} job${n > 1 ? "s" : ""} será(ão) criado(s)`;
}

// ═══════════════════════════════════════════════════════
// AOI — INPUT HANDLERS
// ═══════════════════════════════════════════════════════

function addBboxAoi() {
    const west = parseFloat(document.getElementById("bboxWest").value);
    const south = parseFloat(document.getElementById("bboxSouth").value);
    const east = parseFloat(document.getElementById("bboxEast").value);
    const north = parseFloat(document.getElementById("bboxNorth").value);

    if ([west, south, east, north].some(isNaN)) {
        toast("Preencha todos os campos do BBOX.", "error");
        return;
    }
    if (west >= east || south >= north) {
        toast("BBOX inválido: west < east e south < north.", "error");
        return;
    }

    const geojson = {
        type: "Polygon",
        coordinates: [[
            [west, south], [east, south],
            [east, north], [west, north],
            [west, south],
        ]],
    };

    const customName = document.getElementById("aoiName").value.trim();
    const name = customName || `BBOX ${aoiCounter + 1}`;

    addAoi(name, geojson);

    // Limpa inputs
    document.getElementById("aoiName").value = "";
}

async function uploadShapefile(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
        toast("Processando arquivo...", "info");
        const resp = await fetch("/api/aoi/upload", {
            method: "POST",
            body: formData,
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Erro no upload");
        }

        const data = await resp.json();

        // Usa nome do arquivo como nome da AOI
        const baseName = file.name.replace(/\.(zip|geojson|json)$/i, "");
        addAoi(baseName, data.geojson);
    } catch (err) {
        toast(`Erro: ${err.message}`, "error");
    }

    event.target.value = "";
}

// ═══════════════════════════════════════════════════════
// AUTENTICAÇÃO
// ═══════════════════════════════════════════════════════

async function checkAuthStatus() {
    try {
        const resp = await fetch("/api/auth/status");
        const data = await resp.json();

        document.getElementById("dotGee").className =
            `auth-dot ${data.gee ? "connected" : "disconnected"}`;
        document.getElementById("dotCopernicus").className =
            `auth-dot ${data.copernicus ? "connected" : "disconnected"}`;
        document.getElementById("dotPlanetary").className =
            `auth-dot ${data.planetary ? "connected" : "disconnected"}`;
    } catch {
        // Backend não disponível
    }
}

async function authGee() {
    const projectId = document.getElementById("geeProject").value.trim() || null;
    toast("Autenticando GEE... Verifique o terminal do backend e/ou o navegador.", "info");

    try {
        const body = {};
        if (projectId) body.project_id = projectId;

        const resp = await fetch("/api/auth/gee", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Erro na autenticação GEE");
        }

        const data = await resp.json();
        toast(data.message, "success");
        checkAuthStatus();
    } catch (err) {
        toast(`GEE: ${err.message}`, "error");
    }
}

async function authCopernicus() {
    toast("Iniciando autenticação Copernicus...", "info");

    try {
        const resp = await fetch("/api/auth/copernicus", { method: "POST" });
        const data = await resp.json();

        // Mostra URL + código do device flow na interface (se disponível)
        showDeviceFlowInfo(data);

        if (resp.status === 202) {
            toast("Autenticação em andamento. Complete o login no link mostrado.", "info");
            // Poll para verificar quando auth completar
            const pollAuth = setInterval(async () => {
                const statusResp = await fetch("/api/auth/status");
                const status = await statusResp.json();
                if (status.copernicus) {
                    clearInterval(pollAuth);
                    hideDeviceFlowInfo();
                    toast("Copernicus autenticado com sucesso!", "success");
                    checkAuthStatus();
                }
            }, 3000);
            // Para de pollar após 3 min
            setTimeout(() => clearInterval(pollAuth), 180000);
            return;
        }

        if (!resp.ok) {
            const detail = data.detail || data;
            const msg = typeof detail === "string" ? detail : detail.detail || "Erro";
            if (typeof detail === "object") showDeviceFlowInfo(detail);
            throw new Error(msg);
        }

        hideDeviceFlowInfo();
        toast(data.message, "success");
        checkAuthStatus();
    } catch (err) {
        toast(`Copernicus: ${err.message}`, "error");
    }
}

/**
 * Mostra o painel de device flow com URL + código clicável.
 */
function showDeviceFlowInfo(data) {
    const uri = data.verification_uri;
    const code = data.user_code;
    if (!uri && !code) return;

    hideDeviceFlowInfo();

    const panel = document.createElement("div");
    panel.id = "deviceFlowPanel";
    panel.className = "device-flow-panel";
    panel.innerHTML = `
        <div class="device-flow-title">🔐 Login Copernicus</div>
        ${uri ? `
            <p>Abra o link abaixo e autorize o acesso:</p>
            <a href="${uri}" target="_blank" rel="noopener" class="device-flow-link">${uri}</a>
        ` : ""}
        ${code ? `
            <p style="margin-top:8px">Código de verificação:</p>
            <div class="device-flow-code" onclick="navigator.clipboard.writeText('${code}'); toast('Código copiado!', 'success')" title="Clique para copiar">
                ${code}
            </div>
        ` : ""}
        <p style="margin-top:8px;font-size:11px;color:var(--text-muted)">
            Após autorizar no navegador, aguarde a confirmação aqui.
        </p>
        <button class="btn btn-secondary btn-sm" style="margin-top:8px" onclick="hideDeviceFlowInfo()">Fechar</button>
    `;

    const sidebar = document.querySelector(".sidebar");
    const authPanel = sidebar.querySelector(".panel");
    authPanel.after(panel);
}

function hideDeviceFlowInfo() {
    const panel = document.getElementById("deviceFlowPanel");
    if (panel) panel.remove();
}

// ═══════════════════════════════════════════════════════
// PROVEDOR
// ═══════════════════════════════════════════════════════

function onProviderChange() {
    const provider = document.getElementById("provider").value;
    const isEmbedding = provider === "gee_embedding";

    // Cloud prob: só GEE Sentinel
    document.getElementById("cloudProbContainer").style.display =
        provider === "gee_sentinel" ? "block" : "none";

    // Max cloud: esconde para embedding (não usa cloud masking)
    document.getElementById("maxCloudContainer").style.display =
        isEmbedding ? "none" : "block";

    // Bandas: para embedding as 64 bandas são o padrão, campo menos relevante
    const bandsInput = document.getElementById("bands");
    const resInput = document.getElementById("resolution");

    const defaults = {
        gee_sentinel: { bands: "B2, B3, B4, B8", res: 10, hint: "" },
        gee_landsat:  { bands: "SR_B2, SR_B3, SR_B4, SR_B5", res: 30, hint: "" },
        gee_embedding: {
            bands: "A00–A63 (64 dimensões)",
            res: 10,
            hint: "AlphaEarth Foundations (Google/DeepMind). Embeddings anuais de 64 dimensões, "
                + "10m. Não requer cloud masking. Use datas anuais: ex. 2024-01-01 a 2025-01-01. "
                + "Disponível de 2017 a 2024.",
        },
        copernicus: { bands: "B02, B03, B04, B08", res: 10, hint: "" },
        planetary:  { bands: "blue, green, red, nir08", res: 30, hint: "" },
    };

    const d = defaults[provider];
    bandsInput.placeholder = d ? `padrão: ${d.bands}` : "";
    resInput.placeholder = d ? d.res : "auto";

    // Hint do provedor
    const hintEl = document.getElementById("providerHint");
    if (hintEl) {
        hintEl.textContent = d?.hint || "";
        hintEl.style.display = d?.hint ? "block" : "none";
    }

    // Para embedding, sugere datas anuais se as atuais parecem sub-anuais
    if (isEmbedding) {
        const startEl = document.getElementById("startDate");
        const endEl = document.getElementById("endDate");
        const start = startEl.value;
        const end = endEl.value;

        // Se o range é < 365 dias, sugere ajustar
        if (start && end) {
            const diffDays = (new Date(end) - new Date(start)) / (1000 * 60 * 60 * 24);
            if (diffDays < 360) {
                // Auto-ajusta para ano completo baseado na data inicial
                const year = new Date(start).getFullYear();
                startEl.value = `${year}-01-01`;
                endEl.value = `${year + 1}-01-01`;
                toast(`Embedding é anual — datas ajustadas para ${year}-01-01 → ${year + 1}-01-01`, "info");
            }
        }
    }
}

// ═══════════════════════════════════════════════════════
// PROCESSAMENTO — MULTI-AOI
// ═══════════════════════════════════════════════════════

async function startProcessing() {
    if (aoiList.length === 0) {
        toast("Adicione pelo menos uma AOI antes de processar.", "error");
        return;
    }

    const provider = document.getElementById("provider").value;
    const isEmbedding = provider === "gee_embedding";
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const bandsRaw = document.getElementById("bands").value.trim();
    const resolutionRaw = document.getElementById("resolution").value.trim();
    const maxCloud = parseInt(document.getElementById("maxCloud").value) || 30;
    const cloudProb = parseInt(document.getElementById("cloudProb").value) || 50;

    if (!startDate || !endDate) {
        toast("Preencha as datas.", "error");
        return;
    }

    const btn = document.getElementById("btnProcess");
    btn.disabled = true;
    btn.textContent = `⏳ Enviando ${aoiList.length} job(s)...`;

    let successCount = 0;
    let failCount = 0;

    // Envia um job por AOI
    for (const aoi of aoiList) {
        const body = {
            provider: provider,
            aoi_geojson: aoi.geojson,
            start_date: startDate,
            end_date: endDate,
        };

        // Cloud params só para provedores que usam
        if (!isEmbedding) {
            body.max_cloud = maxCloud;
            body.cloud_prob_threshold = cloudProb;
        }

        if (bandsRaw) {
            body.bands = bandsRaw.split(",").map((b) => b.trim()).filter(Boolean);
        }
        if (resolutionRaw) {
            body.resolution = parseInt(resolutionRaw);
        }

        try {
            const resp = await fetch("/api/process", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || "Erro");
            }

            const job = await resp.json();
            toast(`Job ${job.job_id} criado para "${aoi.name}"`, "success");
            startJobPolling(job.job_id);
            successCount++;
        } catch (err) {
            toast(`Erro em "${aoi.name}": ${err.message}`, "error");
            failCount++;
        }
    }

    renderJobs();

    const summary = `${successCount} job(s) criado(s)` +
        (failCount > 0 ? `, ${failCount} falha(s)` : "");
    toast(summary, successCount > 0 ? "success" : "error");

    btn.disabled = false;
    btn.textContent = "🚀 Processar Todas as AOIs";
}

// ═══════════════════════════════════════════════════════
// POLLING DE JOBS
// ═══════════════════════════════════════════════════════

function startJobPolling(jobId) {
    const intervalId = setInterval(async () => {
        try {
            const resp = await fetch(`/api/jobs/${jobId}`);
            const job = await resp.json();

            renderJobs();

            if (job.status === "completed") {
                clearInterval(intervalId);
                delete pollingIntervals[jobId];
                toast(`Job ${jobId} concluído! Arquivo pronto para download.`, "success");
            } else if (job.status === "failed") {
                clearInterval(intervalId);
                delete pollingIntervals[jobId];
                const msg = job.message || "";
                const isTokenError = msg.toLowerCase().includes("token") ||
                    msg.toLowerCase().includes("expirado") ||
                    msg.toLowerCase().includes("expired") ||
                    msg.toLowerCase().includes("401") ||
                    msg.toLowerCase().includes("não autenticado");
                if (isTokenError) {
                    toast(`Job ${jobId}: Token expirado. Faça login novamente.`, "error");
                    checkAuthStatus();
                } else {
                    toast(`Job ${jobId} falhou: ${msg}`, "error");
                }
            }
        } catch {
            // Ignora erros de polling
        }
    }, 2000);

    pollingIntervals[jobId] = intervalId;
}

async function renderJobs() {
    try {
        const resp = await fetch("/api/jobs");
        const jobs = await resp.json();

        const container = document.getElementById("jobsList");

        if (jobs.length === 0) {
            container.innerHTML = '<p style="font-size:12px;color:var(--text-muted)">Nenhum job ainda.</p>';
            return;
        }

        container.innerHTML = jobs
            .map((job) => {
                const downloadBtn = job.output_file
                    ? `<a class="download-link" href="/api/download/${job.output_file}" download>⬇ Download</a>`
                    : "";

                return `
                <div class="job-item">
                    <div class="job-header">
                        <span class="job-id">#${job.job_id}</span>
                        <span class="job-status ${job.status}">${job.status}</span>
                    </div>
                    <div class="job-message">${job.provider} — ${job.message}</div>
                    <div class="progress-bar">
                        <div class="fill" style="width:${job.progress}%"></div>
                    </div>
                    ${downloadBtn}
                </div>
            `;
            })
            .join("");
    } catch {
        // Silencia erros
    }
}

// ═══════════════════════════════════════════════════════
// TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════

function toast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    const el = document.createElement("div");
    el.className = `toast ${type}`;

    const icon = type === "success" ? "✅" : type === "error" ? "❌" : "ℹ️";
    el.innerHTML = `<span>${icon}</span><span>${message}</span>`;

    container.appendChild(el);
    setTimeout(() => {
        el.style.opacity = "0";
        el.style.transition = "opacity 0.3s";
        setTimeout(() => el.remove(), 300);
    }, 5000);
}

// ═══════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════

checkAuthStatus();
setInterval(checkAuthStatus, 15000);
renderJobs();
renderAoiList();
updateAoiCount();
onProviderChange();
