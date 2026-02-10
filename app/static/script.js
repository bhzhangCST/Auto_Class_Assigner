/**
 * 学生成绩自动分班系统 - 前端脚本
 */

// DOM 元素
const folderInput = document.getElementById('folderInput');
const selectFolderBtn = document.getElementById('selectFolderBtn');
const uploadBtn = document.getElementById('uploadBtn');
const selectedInfo = document.getElementById('selectedInfo');
const fileCount = document.getElementById('fileCount');

const uploadSection = document.getElementById('uploadSection');
const progressSection = document.getElementById('progressSection');
const resultSection = document.getElementById('resultSection');
const errorSection = document.getElementById('errorSection');

const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const resultList = document.getElementById('resultList');
const resultSummary = document.getElementById('resultSummary');
const errorMessage = document.getElementById('errorMessage');

const downloadAllBtn = document.getElementById('downloadAllBtn');
const restartBtn = document.getElementById('restartBtn');
const retryBtn = document.getElementById('retryBtn');

// 状态变量
let selectedFiles = [];
let currentSessionId = null;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 绑定事件
    selectFolderBtn.addEventListener('click', () => folderInput.click());
    folderInput.addEventListener('change', handleFolderSelect);
    uploadBtn.addEventListener('click', handleUpload);
    downloadAllBtn.addEventListener('click', handleDownloadAll);
    restartBtn.addEventListener('click', handleRestart);
    retryBtn.addEventListener('click', handleRestart);
});

/**
 * 处理文件夹选择
 */
function handleFolderSelect(event) {
    const files = Array.from(event.target.files);

    // 过滤 Excel 文件
    selectedFiles = files.filter(file => {
        const ext = file.name.toLowerCase();
        return ext.endsWith('.xlsx') || ext.endsWith('.xls');
    });

    if (selectedFiles.length === 0) {
        alert('未找到有效的 Excel 文件（.xlsx 或 .xls）');
        return;
    }

    // 显示选择信息
    fileCount.textContent = selectedFiles.length;
    selectedInfo.style.display = 'flex';
    uploadBtn.style.display = 'inline-flex';

    // 添加动画
    selectedInfo.classList.add('animate-in');
    uploadBtn.classList.add('animate-in');
}

/**
 * 处理上传
 */
async function handleUpload() {
    if (selectedFiles.length === 0) {
        alert('请先选择文件夹');
        return;
    }

    // 切换到进度视图
    showSection('progress');
    updateProgress(10, '正在上传文件...');

    try {
        // 创建 FormData
        const formData = new FormData();

        for (const file of selectedFiles) {
            // 保持相对路径
            const relativePath = file.webkitRelativePath || file.name;
            formData.append('files', file, relativePath);
        }

        updateProgress(30, '正在解析成绩文件...');

        // 发送请求
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        updateProgress(60, '正在执行分班算法...');

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '上传失败');
        }

        const data = await response.json();

        updateProgress(90, '正在生成结果文件...');

        // 短暂延迟以显示动画
        await sleep(500);

        updateProgress(100, '分班完成！');

        // 显示结果
        await sleep(300);
        showResults(data);

    } catch (error) {
        console.error('Error:', error);
        showError(error.message);
    }
}

/**
 * 显示结果
 */
function showResults(data) {
    currentSessionId = data.session_id;

    // 更新摘要
    resultSummary.textContent = data.message;

    // 清空并生成结果列表
    resultList.innerHTML = '';

    const gradeIcons = ['📚', '📖', '📕', '📗', '📘', '📙'];

    data.results.forEach((result, index) => {
        const icon = gradeIcons[index % gradeIcons.length];

        const itemHtml = `
            <div class="result-item">
                <div class="grade-info">
                    <span class="grade-icon">${icon}</span>
                    <div class="grade-details">
                        <h3>${result.grade}年级</h3>
                        <p>${result.student_count} 名学生 · ${result.class_count} 个班级</p>
                    </div>
                </div>
                <div class="download-buttons">
                    <button class="btn-download" onclick="downloadFile('${result.result_file}')">
                        📥 下载分班结果
                    </button>
                </div>
            </div>
        `;

        resultList.innerHTML += itemHtml;
    });

    showSection('result');
}

/**
 * 下载单个文件
 */
function downloadFile(filename) {
    if (!currentSessionId) {
        alert('会话已过期，请重新上传');
        return;
    }

    const url = `/download/${currentSessionId}/${filename}`;
    window.location.href = url;
}

/**
 * 下载全部文件
 */
function handleDownloadAll() {
    if (!currentSessionId) {
        alert('会话已过期，请重新上传');
        return;
    }

    const url = `/download-all/${currentSessionId}`;
    window.location.href = url;
}

/**
 * 重新开始
 */
function handleRestart() {
    // 清理会话
    if (currentSessionId) {
        fetch(`/cleanup/${currentSessionId}`, { method: 'DELETE' })
            .catch(console.error);
    }

    // 重置状态
    selectedFiles = [];
    currentSessionId = null;
    folderInput.value = '';
    selectedInfo.style.display = 'none';
    uploadBtn.style.display = 'none';

    // 返回上传视图
    showSection('upload');
}

/**
 * 显示错误
 */
function showError(message) {
    errorMessage.textContent = message;
    showSection('error');
}

/**
 * 切换显示区域
 */
function showSection(section) {
    uploadSection.style.display = section === 'upload' ? 'block' : 'none';
    progressSection.style.display = section === 'progress' ? 'block' : 'none';
    resultSection.style.display = section === 'result' ? 'block' : 'none';
    errorSection.style.display = section === 'error' ? 'block' : 'none';
}

/**
 * 更新进度
 */
function updateProgress(percent, text) {
    progressFill.style.width = `${percent}%`;
    if (text) {
        progressText.textContent = text;
    }
}

/**
 * 延迟函数
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
