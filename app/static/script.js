/**
 * ACA Smart Class Assignment System - Frontend Script
 * Two-step flow: upload → configure class sizes → process
 */

let selectedFiles = [];
let currentSessionId = null;
let gradeInfo = [];

const sections = ['uploadSection', 'configSection', 'progressSection', 'resultSection', 'errorSection'];

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('selectFolderBtn').addEventListener('click', () => document.getElementById('folderInput').click());
    document.getElementById('folderInput').addEventListener('change', handleFolderSelect);
    document.getElementById('uploadBtn').addEventListener('click', handleUpload);
    document.getElementById('startAssignBtn').addEventListener('click', handleStartAssign);
    document.getElementById('backBtn').addEventListener('click', () => showSection('uploadSection'));
    document.getElementById('downloadAllBtn').addEventListener('click', handleDownloadAll);
    document.getElementById('restartBtn').addEventListener('click', handleRestart);
    document.getElementById('retryBtn').addEventListener('click', handleRestart);
});

function showSection(id) {
    sections.forEach(s => document.getElementById(s).style.display = s === id ? 'block' : 'none');
}

function handleFolderSelect(event) {
    selectedFiles = Array.from(event.target.files).filter(f => {
        const name = f.name.toLowerCase();
        return name.endsWith('.xlsx') || name.endsWith('.xls');
    });

    if (selectedFiles.length === 0) {
        alert('未找到有效的 Excel 文件（.xlsx 或 .xls）');
        return;
    }

    document.getElementById('fileCount').textContent = selectedFiles.length;
    document.getElementById('selectedInfo').style.display = 'flex';
    document.getElementById('uploadBtn').style.display = 'inline-flex';
}

/**
 * Step 1: Upload files and get grade info for configuration
 */
async function handleUpload() {
    if (selectedFiles.length === 0) return alert('请先选择文件夹');

    showSection('progressSection');
    updateProgress(20, '正在上传并解析文件...');

    try {
        const formData = new FormData();
        for (const file of selectedFiles) {
            formData.append('files', file, file.webkitRelativePath || file.name);
        }

        const response = await fetch('/upload-preview', { method: 'POST', body: formData });
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '上传失败');
        }

        const data = await response.json();
        currentSessionId = data.session_id;
        gradeInfo = data.grades;

        updateProgress(100, '解析完成！');
        await sleep(300);
        showConfigUI(data.grades);
    } catch (error) {
        showError(error.message);
    }
}

/**
 * Show class size configuration UI for each grade
 */
function showConfigUI(grades) {
    const container = document.getElementById('gradeConfigList');
    container.innerHTML = '';

    grades.forEach(g => {
        const div = document.createElement('div');
        div.className = 'grade-config';
        div.dataset.grade = g.grade;

        div.innerHTML = `
            <div class="grade-config-header">
                <h3>📚 ${g.grade_name}年级</h3>
                <span class="tag">${g.student_count} 人 · 原 ${g.original_classes} 班</span>
            </div>
            <div class="class-config-row">
                <div class="config-field">
                    <label>大班</label>
                    <input type="number" class="big-count" value="${g.original_classes}" min="0" max="50"
                           data-grade="${g.grade}" onchange="updatePreview('${g.grade}')">
                    <label>个</label>
                </div>
                <div class="config-field">
                    <label>小班</label>
                    <input type="number" class="small-count" value="0" min="0" max="50"
                           data-grade="${g.grade}" onchange="updatePreview('${g.grade}')">
                    <label>个</label>
                </div>
                <div class="config-field">
                    <label>小班人数</label>
                    <input type="number" class="small-size" value="${Math.floor(g.student_count / g.original_classes * 0.7)}" min="1" max="200"
                           data-grade="${g.grade}" onchange="updatePreview('${g.grade}')">
                    <label>人</label>
                </div>
            </div>
            <div class="class-size-preview" id="preview-${g.grade}"></div>
        `;

        container.appendChild(div);
        updatePreview(g.grade);
    });

    showSection('configSection');
}

/**
 * Update the class size preview text
 */
function updatePreview(grade) {
    const g = gradeInfo.find(x => x.grade === grade);
    if (!g) return;

    const bigCount = parseInt(document.querySelector(`.big-count[data-grade="${grade}"]`).value) || 0;
    const smallCount = parseInt(document.querySelector(`.small-count[data-grade="${grade}"]`).value) || 0;
    const smallSize = parseInt(document.querySelector(`.small-size[data-grade="${grade}"]`).value) || 0;
    const preview = document.getElementById(`preview-${grade}`);

    const totalClasses = bigCount + smallCount;
    if (totalClasses === 0) {
        preview.textContent = '⚠️ 班级数量不能为 0';
        return;
    }

    let bigSize;
    if (smallCount > 0) {
        const remaining = g.student_count - smallCount * smallSize;
        bigSize = bigCount > 0 ? Math.round(remaining / bigCount) : 0;
    } else {
        bigSize = Math.round(g.student_count / bigCount);
    }

    let text = `预计：`;
    if (bigCount > 0) text += `大班 ${bigCount} 个（约 ${bigSize} 人/班）`;
    if (bigCount > 0 && smallCount > 0) text += `，`;
    if (smallCount > 0) text += `小班 ${smallCount} 个（${smallSize} 人/班）`;
    text += `，共 ${totalClasses} 个班`;

    preview.textContent = text;
}

/**
 * Step 2: Start assignment with configured class sizes
 */
async function handleStartAssign() {
    const configs = {};

    gradeInfo.forEach(g => {
        configs[g.grade] = {
            big_count: parseInt(document.querySelector(`.big-count[data-grade="${g.grade}"]`).value) || 0,
            small_count: parseInt(document.querySelector(`.small-count[data-grade="${g.grade}"]`).value) || 0,
            small_size: parseInt(document.querySelector(`.small-size[data-grade="${g.grade}"]`).value) || 0,
        };
    });

    showSection('progressSection');
    updateProgress(30, '正在执行分班算法...');

    try {
        const response = await fetch('/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, configs })
        });

        updateProgress(80, '正在生成结果...');

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '处理失败');
        }

        const data = await response.json();
        updateProgress(100, '分班完成！');
        await sleep(400);
        showResults(data);
    } catch (error) {
        showError(error.message);
    }
}

function showResults(data) {
    currentSessionId = data.session_id;
    document.getElementById('resultSummary').textContent = data.message;

    const list = document.getElementById('resultList');
    list.innerHTML = '';

    const icons = ['📚', '📖', '📕', '📗', '📘', '📙'];

    data.results.forEach((r, i) => {
        list.innerHTML += `
            <div class="result-item">
                <div class="grade-info">
                    <span class="grade-icon">${icons[i % icons.length]}</span>
                    <div class="grade-details">
                        <h3>${r.grade}年级</h3>
                        <p>${r.student_count} 名学生 · ${r.class_count} 个班级</p>
                    </div>
                </div>
                <button class="btn-download" onclick="downloadFile('${r.result_file}')">📥 下载分班结果</button>
            </div>
        `;
    });

    showSection('resultSection');
}

function downloadFile(filename) {
    if (!currentSessionId) return alert('会话已过期，请重新上传');
    window.location.href = `/download/${currentSessionId}/${filename}`;
}

function handleDownloadAll() {
    if (!currentSessionId) return alert('会话已过期，请重新上传');
    window.location.href = `/download-all/${currentSessionId}`;
}

function handleRestart() {
    if (currentSessionId) {
        fetch(`/cleanup/${currentSessionId}`, { method: 'DELETE' }).catch(console.error);
    }
    selectedFiles = [];
    currentSessionId = null;
    gradeInfo = [];
    document.getElementById('folderInput').value = '';
    document.getElementById('selectedInfo').style.display = 'none';
    document.getElementById('uploadBtn').style.display = 'none';
    showSection('uploadSection');
}

function showError(message) {
    document.getElementById('errorMessage').textContent = message;
    showSection('errorSection');
}

function updateProgress(percent, text) {
    document.getElementById('progressFill').style.width = `${percent}%`;
    if (text) document.getElementById('progressText').textContent = text;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
