document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded'); // Отладочная информация

    // DOM Elements
    const sessionSelect = document.getElementById('sessionSelect');
    const newSessionBtn = document.getElementById('newSessionBtn');
    const uploadForm = document.getElementById('uploadForm');
    const inputFile = document.getElementById('inputFile');
    const contextTextarea = document.getElementById('contextText');
    const sessionControls = document.getElementById('sessionControls');
    const startProcessingBtn = document.getElementById('startProcessingBtn');
    const viewLogsBtn = document.getElementById('viewLogsBtn');
    const downloadResultsBtn = document.getElementById('downloadResultsBtn');
    const statusDisplay = document.getElementById('statusDisplay');
    const resultsSection = document.getElementById('resultsSection');
    const resultsTableBody = document.getElementById('resultsTable').querySelector('tbody');
    const loadingIndicator = document.getElementById('loading-indicator');
    const runBtn = document.getElementById('runBtn');
    const progressStatus = document.getElementById('progressStatus');
    const dropZoneContainer = document.getElementById('dropZoneContainer');
    const customChooseFileButton = document.getElementById('customChooseFileButton');
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    const charCounterContext = document.getElementById('charCounterContext'); // Получаем элемент счетчика

    console.log('Elements found:', { // Отладочная информация
        sessionSelect: !!sessionSelect,
        newSessionBtn: !!newSessionBtn,
        uploadForm: !!uploadForm,
        inputFile: !!inputFile,
        contextTextarea: !!contextTextarea,
        sessionControls: !!sessionControls,
        startProcessingBtn: !!startProcessingBtn,
        viewLogsBtn: !!viewLogsBtn,
        downloadResultsBtn: !!downloadResultsBtn,
        statusDisplay: !!statusDisplay,
        resultsSection: !!resultsSection,
        resultsTableBody: !!resultsTableBody,
        loadingIndicator: !!loadingIndicator,
        runBtn: !!runBtn,
        progressStatus: !!progressStatus,
        dropZoneContainer: !!dropZoneContainer,
        customChooseFileButton: !!customChooseFileButton,
        fileNameDisplay: !!fileNameDisplay,
        charCounterContext: !!charCounterContext // Логируем счетчик
    });

    let currentSessionId = null;
    let pollingInterval = null;
    let ws = null;
    let resultsTable = null;

    // --- Loading Indicator Functions ---
    function showLoading() {
        console.log('Showing loading indicator'); // Отладочная информация
        if (loadingIndicator) loadingIndicator.style.display = 'block';
    }

    function hideLoading() {
        console.log('Hiding loading indicator'); // Отладочная информация
        if (loadingIndicator) loadingIndicator.style.display = 'none';
    }

    // --- UI State Functions ---
    function showNewSessionUI() {
        console.log('Showing new session UI'); // Отладочная информация
        if (uploadForm) uploadForm.style.display = 'block';
        if (sessionControls) sessionControls.style.display = 'none';
        if (resultsSection) resultsSection.style.display = 'none';
        if (sessionSelect) sessionSelect.value = '';
        currentSessionId = null;
        clearResultsTable();
        updateStatus('Ready to create new session');
    }

    function showCurrentSessionUI(sessionId) {
        console.log('Showing current session UI:', sessionId); // Отладочная информация
        if (uploadForm) uploadForm.style.display = 'none';
        if (sessionControls) sessionControls.style.display = 'none'; // Скрываем sessionControls по умолчанию
        currentSessionId = sessionId;
    }

    function updateStatus(message) {
        console.log('Updating status:', message); // Отладочная информация
        if (statusDisplay) statusDisplay.textContent = message;
    }

    function clearResultsTable() {
        console.log('Clearing results table'); // Отладочная информация
        if (resultsTableBody) resultsTableBody.innerHTML = '';
    }

    // --- Event Listeners ---
    if (newSessionBtn) {
        console.log('Adding click listener to newSessionBtn'); // Отладочная информация
        newSessionBtn.addEventListener('click', () => {
            console.log('New Session button clicked'); // Отладочная информация
            showNewSessionUI();
        });
    }

    if (uploadForm) {
        console.log('Adding submit listener to uploadForm'); // Отладочная информация
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            showLoading();
            if (runBtn) runBtn.style.display = 'none';
            uploadForm.style.display = 'none';
            if (progressStatus) {
                progressStatus.style.display = 'block';
                progressStatus.textContent = 'Processing...';
            }
            const formData = new FormData();
            if (inputFile && inputFile.files[0]) {
                formData.append('file', inputFile.files[0]);
            }
            if (contextTextarea && contextTextarea.value.trim() !== "") {
                formData.append('context_text', contextTextarea.value.trim());
            }

            // Добавляем состояния чекбоксов
            const standardPipelineCheckbox = document.getElementById('standardPipeline');
            const llmDeepSearchPipelineCheckbox = document.getElementById('llmDeepSearchPipeline');

            if (standardPipelineCheckbox) {
                formData.append('run_standard_pipeline', standardPipelineCheckbox.checked);
            }
            if (llmDeepSearchPipelineCheckbox) {
                formData.append('run_llm_deep_search_pipeline', llmDeepSearchPipelineCheckbox.checked);
            }

            try {
                const response = await fetch('/api/sessions', {
                    method: 'POST',
                    body: formData
                });
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to create session');
                }
                const sessionData = await response.json();
                currentSessionId = sessionData.session_id;
                await startProcessingImmediately(currentSessionId);
            } catch (error) {
                if (progressStatus) {
                    progressStatus.style.display = 'block';
                    progressStatus.textContent = `Error: ${error.message}`;
                    progressStatus.style.color = 'red';
                }
            } finally {
                hideLoading();
            }
        });
    }

    startProcessingBtn.addEventListener('click', async () => {
        if (!currentSessionId) return;
        
        showLoading();
        try {
            const response = await fetch(`/api/sessions/${currentSessionId}/start`, {
                method: 'POST'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start processing');
            }

            updateStatus('Processing started...');
            startPollingStatus(currentSessionId);
        } catch (error) {
            console.error('Error starting processing:', error);
            updateStatus(`Error: ${error.message}`);
        } finally {
            hideLoading();
        }
    });

    // --- API Functions ---
    async function fetchSessions() {
        showLoading();
        try {
            const response = await fetch('/api/sessions');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const sessions = await response.json();
            populateSessionSelect(sessions);
        } catch (error) {
            console.error('Error fetching sessions:', error);
            updateStatus(`Error loading sessions: ${error.message}`);
        } finally {
            hideLoading();
        }
    }

    async function fetchSessionData(sessionId) {
        if (!sessionId) return;
        showLoading();
        try {
            const response = await fetch(`/api/sessions/${sessionId}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const sessionData = await response.json();
            showCurrentSessionUI(sessionId); // Это скроет sessionControls
            updateStatus(`Status: ${sessionData.status}`);
            window.expectedTotalCompanies = sessionData.total_companies || sessionData.last_processed_count || 0;
            
            if (sessionData.status === 'completed' || sessionData.status === 'error') {
                await fetchAndDisplayResults(sessionId);
                if (sessionData.status === 'completed') {
                    updateProgressBar(window.expectedTotalCompanies, window.expectedTotalCompanies, true);
                }
                ensureResultsControlsAvailable(); // Создаем кнопки, если их нет
                makeResultsControlsVisible(true); // Делаем их видимыми
            } else {
                makeResultsControlsVisible(false); // Скрываем для других статусов
            }
        } catch (error) {
            console.error('Error fetching session data:', error);
            updateStatus(`Error: ${error.message}`);
        } finally {
            hideLoading();
        }
    }

    async function fetchAndDisplayResults(sessionId) {
        console.log(`fetchAndDisplayResults вызвана для сессии: ${sessionId}`); // Новый лог
        showLoading();
        try {
            const response = await fetch(`/api/sessions/${sessionId}/results`);
            console.log(`Статус ответа для /results: ${response.status}, Content-Type: ${response.headers.get('Content-Type')}`); // Новый лог

            if (!response.ok) {
                console.error(`Ответ не OK: статус ${response.status}`); // Новый лог
                try {
                    const errorText = await response.text();
                    console.error(`Тело ошибки: ${errorText}`);
                } catch (e) {
                    console.error('Не удалось прочитать тело ошибки:', e);
                }
                return;
            }
            
            const responseText = await response.text();
            console.log('Ответ сервера (текст):', responseText);

            const results = JSON.parse(responseText);
            console.log('Fetched results (распарсенные):', results);

            displayResultsInTable(results);
            const total = window.expectedTotalCompanies || results.length;
            updateProgressBar(results.length, total, false);
            resultsSection.style.display = 'block';
            if (progressStatus) progressStatus.style.display = 'block';
            if (newSessionBtn) newSessionBtn.style.display = 'inline-block';
        } catch (error) {
            console.error('Ошибка в fetchAndDisplayResults:', error);
            if (error instanceof SyntaxError) {
                console.error('Ошибка парсинга JSON. Ответ сервера не является валидным JSON. Текст ответа выше.');
            }
        } finally {
            hideLoading();
        }
    }

    function displayResultsInTable(results) {
        clearResultsTable();
        if (!results || results.length === 0) {
            resultsTableBody.innerHTML = '<tr><td colspan="2" style="text-align:center;">Still in progress... No results found.</td></tr>';
            return;
        }

        results.forEach(row => {
            const tr = document.createElement('tr');
        
            // Company Name
            const name = escapeHtml(row.Company_Name || '');
            console.log('Adding to table:', name); // <--- ДОБАВЛЕН ЭТОТ ЛОГ
        
            // Description (с переводом переносов строк в <br>)
            let descriptionHtml = escapeHtml(row.Description || '');
            descriptionHtml = descriptionHtml.replace(/\n/g, '<br>');
        
            // Добавляем ссылку на официальный сайт
            if (row.Official_Website && row.Official_Website !== 'Not found') {
                const link = escapeHtml(row.Official_Website);
                descriptionHtml += `<br><br>Homepage: <a href="${link}" target="_blank">${link}</a>`;
            }
        
            // Добавляем ссылку на LinkedIn
            if (row.LinkedIn_URL && row.LinkedIn_URL !== 'Not found') {
                const link = escapeHtml(row.LinkedIn_URL);
                descriptionHtml += `<br>LinkedIn: <a href="${link}" target="_blank">${link}</a>`;
            }
        
            tr.innerHTML = `
                <td>${name}</td>
                <td>${descriptionHtml}</td>
            `;
            resultsTableBody.appendChild(tr);
        });
    }

    function populateSessionSelect(sessions) {
        sessionSelect.innerHTML = '<option value="">-- Select a session --</option>';
        sessions.forEach(session => {
            const option = document.createElement('option');
            option.value = session.session_id;
            option.textContent = `${session.session_id} (${session.status})`;
            sessionSelect.appendChild(option);
        });
    }

    function startPollingStatus(sessionId) {
        if (pollingInterval) {
            clearInterval(pollingInterval);
        }
        pollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/sessions/${sessionId}`);
                if (!response.ok) return;
                const sessionData = await response.json();
                updateStatus(`Status: ${sessionData.status}`);
                // Сохраняем ожидаемое количество компаний для прогресс-бара
                window.expectedTotalCompanies = sessionData.total_companies || sessionData.last_processed_count || window.expectedTotalCompanies || 0;
                await fetchAndDisplayResults(sessionId);
                if (sessionData.status === 'completed' || sessionData.status === 'error') {
                    stopPollingStatus();
                    await fetchAndDisplayResults(sessionId);
                    if (sessionData.status === 'completed'){
                        updateProgressBar(window.expectedTotalCompanies, window.expectedTotalCompanies, true);
                    }
                    ensureResultsControlsAvailable();
                    makeResultsControlsVisible(true);
                }
            } catch (error) {
                // Не показываем тревожных сообщений, если результатов ещё нет
            }
        }, 2000);
    }

    function stopPollingStatus() {
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
        if (progressStatus) progressStatus.style.display = 'none';
    }

    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe
            .toString()
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    async function startProcessingImmediately(sessionId) {
        showLoading();
        if (progressStatus) {
            progressStatus.style.display = 'block';
            progressStatus.textContent = 'Processing...';
            progressStatus.style.color = '#007bff';
        }
        try {
            const response = await fetch(`/api/sessions/${sessionId}/start`, {
                method: 'POST'
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start processing');
            }
            startPollingStatus(sessionId);
        } catch (error) {
            if (progressStatus) {
                progressStatus.style.display = 'block';
                progressStatus.textContent = `Error: ${error.message}`;
                progressStatus.style.color = 'red';
            }
        } finally {
            hideLoading();
        }
    }

    function showResultsControls() {
        if (sessionControls) {
            sessionControls.style.display = 'block';
            startProcessingBtn.style.display = 'none';
            viewLogsBtn.style.display = 'inline-block';
            downloadResultsBtn.style.display = 'inline-block';
            downloadResultsBtn.textContent = 'Download results (CSV)';

            // --- Add Download Archive Button ---
            let downloadArchiveBtn = document.getElementById('downloadArchiveBtn');
            if (!downloadArchiveBtn) {
                downloadArchiveBtn = document.createElement('button');
                downloadArchiveBtn.id = 'downloadArchiveBtn';
                downloadArchiveBtn.textContent = 'Download Full Archive (ZIP)';
                downloadArchiveBtn.className = 'button results-button'; // Используем тот же класс, что и другие кнопки результатов
                downloadArchiveBtn.style.marginLeft = '10px'; // Небольшой отступ
                sessionControls.appendChild(downloadArchiveBtn);
            }
            downloadArchiveBtn.style.display = 'inline-block';
            downloadArchiveBtn.onclick = () => downloadSessionArchive(currentSessionId);
            // --- End Add Download Archive Button ---

            let restartBtn = document.getElementById('restartProcessingBtn');
            if (restartBtn) restartBtn.remove();
        }
    }

    // --- Function to Download Session Archive ---
    function downloadSessionArchive(sessionId) {
        if (!sessionId) {
            alert('No active session selected to download archive.');
            return;
        }
        console.log(`Attempting to download archive for session: ${sessionId}`);
        // Используем window.location.href для простого инициирования скачивания
        window.location.href = `/api/sessions/${sessionId}/download_archive`;
    }
    // --- End Function to Download Session Archive ---

    if (newSessionBtn) {
        newSessionBtn.addEventListener('click', () => {
            if (uploadForm) {
                uploadForm.reset();
                uploadForm.style.display = 'block';
            }
            if (runBtn) runBtn.style.display = 'inline-block';
            if (resultsSection) resultsSection.style.display = 'none';
            if (sessionControls) sessionControls.style.display = 'none';
            if (progressStatus) progressStatus.style.display = 'none';
            if (newSessionBtn) newSessionBtn.style.display = 'none';
            currentSessionId = null;
            // Скрываем кнопку скачивания архива при создании новой сессии
            const downloadArchiveBtn = document.getElementById('downloadArchiveBtn');
            if (downloadArchiveBtn) {
                downloadArchiveBtn.style.display = 'none';
            }
            makeResultsControlsVisible(false); // Скрываем все кнопки результатов
        });
    }

    if (downloadResultsBtn) {
        downloadResultsBtn.onclick = async () => {
            if (!currentSessionId) {
                alert('No active session selected to download results.');
                return;
            }
            try {
                const response = await fetch(`/api/sessions/${currentSessionId}/results`);
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Failed to fetch results for download');
                }
                const results = await response.json();
                if (!results || results.length === 0) {
                    alert('No results available to download for this session.');
                    return;
                }

                const csv = convertResultsToCSV(results);
                const blob = new Blob(["\uFEFF" + csv], { type: 'text/csv;charset=utf-8;' }); // Added BOM for Excel UTF-8 compatibility
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                // Формируем имя файла для скачивания, используя currentSessionId
                a.download = `${currentSessionId}_results.csv`; 
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch (e) {
                console.error('Download results error:', e);
                alert(`Failed to download results: ${e.message}`);
            }
        };
    }

    if (viewLogsBtn) {
        viewLogsBtn.onclick = async () => {
            if (!currentSessionId) return;
            try {
                const response = await fetch(`/api/sessions/${currentSessionId}/logs/pipeline`);
                if (!response.ok) throw new Error('Failed to download log');
                const logText = await response.text();
                const blob = new Blob([logText], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'pipeline.log';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch (e) {
                alert('Failed to download log');
            }
        };
    }

    function convertResultsToCSV(results) {
        if (!results || !results.length) return '';
        const keys = Object.keys(results[0]);
        const header = keys.join(',');
        const rows = results.map(row => keys.map(k => '"' + (row[k] ? String(row[k]).replace(/"/g, '""') : '') + '"').join(','));
        return header + '\n' + rows.join('\n');
    }

    function updateProgressBar(processed, total, completed) {
        let progressStatus = document.getElementById('progressStatus');
        if (!progressStatus) return;
        if (!completed) {
            progressStatus.style.display = 'block';
            progressStatus.style.color = '#007bff';
            progressStatus.textContent = `Processing... ${processed} of ${total} processed`;
        } else {
            progressStatus.style.display = 'block';
            progressStatus.style.color = 'green';
            progressStatus.textContent = `Completed: ${processed} of ${total} processed`;
        }
    }

    // Connect WebSocket when page loads
    // connectWebSocket(); // Assuming this was commented out or removed intentionally earlier

    // Initial load
    console.log('Starting initial load');

    // --- Character Counter for Context Textarea ---
    if (contextTextarea && charCounterContext) {
        const maxLength = contextTextarea.maxLength;
        charCounterContext.textContent = `${maxLength} characters remaining`; // Начальное значение

        contextTextarea.addEventListener('input', () => {
            const currentLength = contextTextarea.value.length;
            const remaining = maxLength - currentLength;
            charCounterContext.textContent = `${remaining} characters remaining`;

            if (remaining < 0) {
                charCounterContext.style.color = 'red';
                // Текст уже не должен вводиться сверх maxlength, но для надежности:
                // contextTextarea.value = contextTextarea.value.substring(0, maxLength);
                // charCounterContext.textContent = `0 characters remaining`;
            } else if (remaining < 20) { // Если остается мало символов, подсветим
                charCounterContext.style.color = 'orange';
            } else {
                charCounterContext.style.color = '#6c757d'; // Стандартный цвет
            }
        });
    }

    // --- Drag & Drop Event Listeners for dropZoneContainer ---
    if (dropZoneContainer && inputFile && customChooseFileButton && fileNameDisplay) {
        customChooseFileButton.addEventListener('click', () => {
            inputFile.click();
        });

        dropZoneContainer.addEventListener('dragover', (event) => {
            event.preventDefault();
            dropZoneContainer.classList.add('dragover');
        });

        dropZoneContainer.addEventListener('dragleave', (event) => {
            dropZoneContainer.classList.remove('dragover');
        });

        dropZoneContainer.addEventListener('drop', (event) => {
            event.preventDefault();
            dropZoneContainer.classList.remove('dragover');

            const files = event.dataTransfer.files;
            if (files.length > 0) {
                inputFile.files = files;
                const fileName = files[0].name;
                fileNameDisplay.textContent = `File selected: ${fileName}`;
                fileNameDisplay.style.color = '#28a745';
                console.log('File(s) dropped and assigned to input:', files);
            } else {
                fileNameDisplay.textContent = '';
            }
        });

        inputFile.addEventListener('change', function() {
            if (this.files && this.files.length > 0) {
                fileNameDisplay.textContent = `File selected: ${this.files[0].name}`;
                fileNameDisplay.style.color = '#28a745';
            } else {
                fileNameDisplay.textContent = '';
            }
        });
    }

    // --- Function to ensure result control buttons are in the DOM ---
    function ensureResultsControlsAvailable() {
        if (!sessionControls) return;

        if (!document.getElementById('viewLogsBtn')) { // Предполагаем, что эта кнопка всегда должна быть, если есть sessionControls
            // Это условие может потребовать пересмотра, если viewLogsBtn не всегда создается заранее
            console.warn("viewLogsBtn not found during ensureResultsControlsAvailable. Controls might not be fully initialized.");
        }

        if (!document.getElementById('downloadResultsBtn')) {
            console.warn("downloadResultsBtn not found during ensureResultsControlsAvailable.");
        }
        
        let downloadArchiveBtn = document.getElementById('downloadArchiveBtn');
        if (!downloadArchiveBtn) {
            downloadArchiveBtn = document.createElement('button');
            downloadArchiveBtn.id = 'downloadArchiveBtn';
            downloadArchiveBtn.textContent = 'Download Full Archive (ZIP)';
            downloadArchiveBtn.className = 'button results-button'; 
            downloadArchiveBtn.style.marginLeft = '10px'; 
            sessionControls.appendChild(downloadArchiveBtn);
            downloadArchiveBtn.onclick = () => downloadSessionArchive(currentSessionId);
        }
        // При создании кнопки по умолчанию скрыты, их видимостью управляет makeResultsControlsVisible
        viewLogsBtn.style.display = 'none';
        downloadResultsBtn.style.display = 'none';
        downloadArchiveBtn.style.display = 'none';
    }

    // --- Function to manage visibility of result control buttons ---
    function makeResultsControlsVisible(visible) {
        if (sessionControls) {
            sessionControls.style.display = visible ? 'block' : 'none';
            if (viewLogsBtn) viewLogsBtn.style.display = visible ? 'inline-block' : 'none';
            if (downloadResultsBtn) {
                downloadResultsBtn.style.display = visible ? 'inline-block' : 'none';
                downloadResultsBtn.textContent = 'Download results (CSV)';
            }
            const downloadArchiveBtn = document.getElementById('downloadArchiveBtn');
            if (downloadArchiveBtn) downloadArchiveBtn.style.display = visible ? 'inline-block' : 'none';
            
            // Кнопка Start Processing должна быть скрыта, если видны кнопки результатов
            if (startProcessingBtn) startProcessingBtn.style.display = visible ? 'none' : 'inline-block'; 
        }
    }
});
