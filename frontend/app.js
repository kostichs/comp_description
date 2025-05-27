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

    // --- HubSpot Toggle Management Functions ---
    function enableHubSpotToggle() {
        const writeToHubspotCheckbox = document.getElementById('writeToHubspot');
        const toggleLabel = document.querySelector('label[for="writeToHubspot"]');
        if (writeToHubspotCheckbox) {
            writeToHubspotCheckbox.disabled = false;
            writeToHubspotCheckbox.style.opacity = '1';
        }
        if (toggleLabel) {
            toggleLabel.style.opacity = '1';
            toggleLabel.style.cursor = 'pointer';
            toggleLabel.title = 'Enable/disable writing results to HubSpot CRM';
        }
    }

    function disableHubSpotToggle() {
        const writeToHubspotCheckbox = document.getElementById('writeToHubspot');
        const toggleLabel = document.querySelector('label[for="writeToHubspot"]');
        if (writeToHubspotCheckbox) {
            writeToHubspotCheckbox.disabled = true;
            writeToHubspotCheckbox.style.opacity = '0.6';
        }
        if (toggleLabel) {
            toggleLabel.style.opacity = '0.6';
            toggleLabel.style.cursor = 'not-allowed';
            const isEnabled = writeToHubspotCheckbox.checked;
            toggleLabel.title = `HubSpot writing is ${isEnabled ? 'ENABLED' : 'DISABLED'} for this session (cannot be changed during processing)`;
        }
    }

    // --- UI State Functions ---
    async function showNewSessionUI() {
        console.log('Showing new session UI'); // Отладочная информация
        
        // Отменяем активную сессию если она есть
        if (currentSessionId) {
            console.log(`Cancelling active session: ${currentSessionId}`);
            showLoading(); // Показываем индикатор загрузки
            try {
                const response = await fetch(`/api/sessions/${currentSessionId}/cancel`, {
                    method: 'POST'
                });
                if (response.ok) {
                    const result = await response.json();
                    console.log(`Successfully cancelled session: ${currentSessionId}`, result);
                    updateStatus(`Previous session cancelled: ${result.status}`);
                    
                    // Ждем немного, чтобы отмена успела обработаться
                    await new Promise(resolve => setTimeout(resolve, 1000));
                } else {
                    console.warn(`Failed to cancel session: ${currentSessionId}, status: ${response.status}`);
                    updateStatus('Failed to cancel previous session');
                }
            } catch (error) {
                console.error(`Error cancelling session ${currentSessionId}:`, error);
                updateStatus('Error cancelling previous session');
            } finally {
                hideLoading(); // Скрываем индикатор загрузки
            }
        }
        
        if (uploadForm) uploadForm.style.display = 'block';
        if (sessionControls) sessionControls.style.display = 'none';
        if (resultsSection) resultsSection.style.display = 'none';
        if (progressStatus) progressStatus.style.display = 'none';
        if (sessionSelect) sessionSelect.value = '';
        if (newSessionBtn) newSessionBtn.style.display = 'none';
        if (runBtn) runBtn.style.display = 'inline-block';
        currentSessionId = null;
        clearResultsTable();
        updateStatus('Ready to create new session');
        
        // Скрываем кнопки управления результатами
        makeResultsControlsVisible(false);
        
        // Очищаем поля формы
        if (inputFile) inputFile.value = '';
        if (contextTextarea) contextTextarea.value = '';
        if (document.getElementById('fileNameDisplay')) {
            document.getElementById('fileNameDisplay').textContent = '';
        }
        
        // Сбрасываем состояние HubSpot toggle на включенное и активируем его
        const writeToHubspotCheckbox = document.getElementById('writeToHubspot');
        if (writeToHubspotCheckbox) {
            writeToHubspotCheckbox.checked = true;
        }
        enableHubSpotToggle();
        
        // Останавливаем polling если он активен
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
        
        // Очищаем глобальные переменные
        window.deduplicationInfo = null;
        
        console.log('New session UI fully reset');
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
        // Также очищаем статус
        if (statusDisplay) statusDisplay.textContent = '';
    }

    // --- Event Listeners ---
    if (newSessionBtn) {
        console.log('Adding click listener to newSessionBtn'); // Отладочная информация
        newSessionBtn.addEventListener('click', async () => {
            console.log('New Session button clicked'); // Отладочная информация
            await showNewSessionUI();
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

            // LLM Deep Search pipeline всегда включен
            formData.append('run_llm_deep_search_pipeline', true);
            
            // Добавляем состояние HubSpot toggle
            const writeToHubspotCheckbox = document.getElementById('writeToHubspot');
            if (writeToHubspotCheckbox) {
                formData.append('write_to_hubspot', writeToHubspotCheckbox.checked);
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
                // Показываем кнопку New Session при любой ошибке
                if (newSessionBtn) {
                    newSessionBtn.style.display = 'inline-block';
                }
                // Показываем форму загрузки снова
                if (uploadForm) {
                    uploadForm.style.display = 'block';
                }
                if (runBtn) {
                    runBtn.style.display = 'inline-block';
                }
                // Активируем HubSpot toggle обратно при ошибке создания сессии
                enableHubSpotToggle();
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
            // Показываем кнопку New Session при ошибке
            if (newSessionBtn) {
                newSessionBtn.style.display = 'inline-block';
            }
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
            // Показываем кнопку New Session при ошибке загрузки сессий
            if (newSessionBtn) {
                newSessionBtn.style.display = 'inline-block';
            }
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
            
            // Сохраняем информацию о дедупликации, если она есть
            if (sessionData.deduplication_info) {
                window.deduplicationInfo = sessionData.deduplication_info;
                console.log('Deduplication info in fetchSessionData:', sessionData.deduplication_info);
            }
            
            // Управляем состоянием HubSpot toggle в зависимости от статуса сессии
            if (sessionData.status === 'running' || sessionData.status === 'queued') {
                disableHubSpotToggle(); // Деактивируем для активных сессий
            } else {
                enableHubSpotToggle(); // Активируем для завершенных/ошибочных сессий
            }
            
            if (sessionData.status === 'completed' || sessionData.status === 'error') {
                // Показываем секцию результатов, как только узнаем, что процесс завершен или есть ошибка.
                // Таблица либо заполнится, либо покажет сообщение "нет результатов" / "ошибка загрузки".
                if (resultsSection) resultsSection.style.display = 'block';

                await fetchAndDisplayResults(sessionId, sessionData);
                if (sessionData.status === 'completed') {
                    // Передаем sessionData для корректного определения total и processed
                    // processed будет равен total, так как completed = true
                    let finalCount = (sessionData.deduplication_info && sessionData.deduplication_info.final_count)
                                     ? sessionData.deduplication_info.final_count
                                     : sessionData.total_companies;
                    updateProgressBar(finalCount, finalCount, true, sessionData);
                }
                ensureResultsControlsAvailable(); // Создаем кнопки, если их нет
                makeResultsControlsVisible(true); // Делаем их видимыми
            } else {
                await fetchAndDisplayResults(sessionId, sessionData);
                makeResultsControlsVisible(false); // Скрываем для других статусов
            }
        } catch (error) {
            console.error('Error fetching session data:', error);
            updateStatus(`Error: ${error.message}`);
            // Показываем кнопку New Session при ошибке загрузки данных сессии
            if (newSessionBtn) {
                newSessionBtn.style.display = 'inline-block';
            }
        } finally {
            hideLoading();
        }
    }

    async function fetchAndDisplayResults(sessionId, sessionData) {
        console.log(`fetchAndDisplayResults вызвана для сессии: ${sessionId}`);
        showLoading();
        try {
            const response = await fetch(`/api/sessions/${sessionId}/results`);
            console.log(`Статус ответа для /results: ${response.status}, Content-Type: ${response.headers.get('Content-Type')}`);

            if (!response.ok) {
                console.error(`Ответ не OK: статус ${response.status}`);
                let errorMsg = `Failed to load results. Status: ${response.status}`;
                try {
                    const errorData = await response.json(); // Попытка прочитать JSON для деталей
                    errorMsg = errorData.detail || errorMsg; 
                } catch (e) {
                    // Если тело не JSON или пустое, используем стандартное сообщение
                    console.warn('Could not parse error response as JSON or response was empty.');
                }
                displayResultsInTable(null, errorMsg); // Отображаем ошибку в таблице
                // resultsSection уже должен быть видим, если статус completed
                hideLoading();
                return;
            }
            
            const responseText = await response.text();
            // console.log('Ответ сервера (текст) в fetchAndDisplayResults:', responseText); // Можно раскомментировать для отладки

            const results = JSON.parse(responseText);
            console.log('Fetched results (распарсенные) в fetchAndDisplayResults:', results);

            displayResultsInTable(results); // Отображаем результаты
            
            const processed = results.length; // Количество фактически полученных строк результатов
            let totalForProgress = sessionData.total_companies; // По умолчанию из sessionData

            if (sessionData.deduplication_info && sessionData.deduplication_info.final_count) {
                totalForProgress = sessionData.deduplication_info.final_count;
            }
            
            console.log(`fetchAndDisplayResults: Progress: ${processed} of ${totalForProgress} (original total: ${sessionData.total_companies})`);
            console.log(`fetchAndDisplayResults: Deduplication info: ${JSON.stringify(sessionData.deduplication_info)}`);
            
            // Обновляем прогресс-бар, передавая sessionData. completed = false, т.к. это обновление по ходу
            // Если статус сессии 'completed', то completed=true будет установлено выше, в fetchSessionData
            const isCompleted = sessionData.status === 'completed';
            updateProgressBar(processed, totalForProgress, isCompleted, sessionData);
            
            resultsSection.style.display = 'block';
            if (document.getElementById('progressStatus')) document.getElementById('progressStatus').style.display = 'block'; // Используем getElementById для progressStatus
            if (newSessionBtn) newSessionBtn.style.display = 'inline-block';
        } catch (error) {
            console.error('Ошибка в fetchAndDisplayResults:', error);
            let detailedErrorMsg = 'Error fetching or processing results.';
            if (error instanceof SyntaxError) {
                detailedErrorMsg = 'Error parsing results data (invalid JSON).';
                console.error('Ошибка парсинга JSON. Ответ сервера не является валидным JSON. Текст ответа выше.');
            }
            displayResultsInTable(null, detailedErrorMsg); // Отображаем ошибку в таблице
            // resultsSection уже должен быть видим, если статус completed или error
        } finally {
            hideLoading();
        }
    }

    function displayResultsInTable(results, errorMessage) {
        clearResultsTable();
        if (errorMessage) {
            resultsTableBody.innerHTML = `<tr><td colspan="2" style="text-align:center; color:red;">${escapeHtml(errorMessage)}</td></tr>`;
            return;
        }
        if (!results || results.length === 0) {
            resultsTableBody.innerHTML = '<tr><td colspan="2" style="text-align:center;">No results found or processing is still in progress.</td></tr>';
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
                const sessionData = await response.json(); // Получаем свежие данные о сессии
                updateStatus(`Status: ${sessionData.status}`);
                
                await fetchAndDisplayResults(sessionId, sessionData); 
                
                if (sessionData.status === 'completed' || sessionData.status === 'error') {
                    stopPollingStatus();
                    // Активируем HubSpot toggle когда сессия завершена
                    enableHubSpotToggle();
                    if (sessionData.status === 'completed'){
                        let finalCount = (sessionData.deduplication_info && sessionData.deduplication_info.final_count) 
                                         ? sessionData.deduplication_info.final_count 
                                         : sessionData.total_companies;
                        updateProgressBar(finalCount, finalCount, true, sessionData);
                    }
                    ensureResultsControlsAvailable();
                    makeResultsControlsVisible(true);
                }
            } catch (error) {
                // Не показываем тревожных сообщений, если результатов ещё нет
                // Можно добавить console.error для отладки, если необходимо
                // console.error('Error in polling interval:', error);
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
        // Деактивируем HubSpot toggle когда начинается обработка
        disableHubSpotToggle();
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
            // Показываем кнопку New Session при ошибке запуска
            if (newSessionBtn) {
                newSessionBtn.style.display = 'inline-block';
            }
            // Показываем форму загрузки снова
            if (uploadForm) {
                uploadForm.style.display = 'block';
            }
            if (runBtn) {
                runBtn.style.display = 'inline-block';
            }
            // Активируем HubSpot toggle обратно при ошибке
            enableHubSpotToggle();
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

    function updateProgressBar(processedCount, totalCountArg, completed, sessionData) {
        const progressStatus = document.getElementById('progressStatus');
        if (!progressStatus) {
            console.error("updateProgressBar: progressStatus element not found!");
            return;
        }

        console.log('[NEW] updateProgressBar ARGS:', { processedCount, totalCountArg, completed, sessionDataStatus: sessionData ? sessionData.status : 'N/A' });
        if (sessionData) {
            console.log('[NEW] updateProgressBar sessionData details:', {
                total_companies: sessionData.total_companies,
                companies_count: sessionData.companies_count, // Может быть полезно для отладки
                initial_upload_count: sessionData.initial_upload_count,
                dedup_info: sessionData.deduplication_info ? JSON.stringify(sessionData.deduplication_info) : 'N/A'
            });
        }

        let effectiveTotal = 0;
        let effectiveProcessed = processedCount; // По умолчанию
        let deduplicationTextParts = []; // Массив для частей текста о дедупликации

        if (sessionData) {
            // 1. Приоритет: sessionData.total_companies (обновляется после дедупликации)
            if (typeof sessionData.total_companies === 'number' && sessionData.total_companies > 0) {
                effectiveTotal = sessionData.total_companies;
                console.log(`[NEW] updateProgressBar: Case 1 - Using sessionData.total_companies = ${effectiveTotal}`);
            }
            // 2. Запасной: sessionData.deduplication_info.final_count
            else if (sessionData.deduplication_info && typeof sessionData.deduplication_info.final_count === 'number' && sessionData.deduplication_info.final_count > 0) {
                effectiveTotal = sessionData.deduplication_info.final_count;
                console.log(`[NEW] updateProgressBar: Case 2 - Using sessionData.deduplication_info.final_count = ${effectiveTotal}`);
            }
            // 3. Если процесс еще не завершен, и totalCountArg (обычно длина results) больше 0
            else if (!completed && typeof totalCountArg === 'number' && totalCountArg > 0) {
                effectiveTotal = totalCountArg;
                console.log(`[NEW] updateProgressBar: Case 3 - Using totalCountArg (argument) = ${effectiveTotal} (intermediate)`);
            }
            // 4. Крайний случай: sessionData.initial_upload_count (чтобы избежать 0 из 0)
            else if (typeof sessionData.initial_upload_count === 'number' && sessionData.initial_upload_count > 0) {
                effectiveTotal = sessionData.initial_upload_count;
                console.log(`[NEW] updateProgressBar: Case 4 - Using sessionData.initial_upload_count = ${effectiveTotal} (fallback)`);
            }
             // 5. Если все еще 0, но totalCountArg (аргумент) не 0, используем его, чтобы не было 0 из 0.
            else if (typeof totalCountArg === 'number' && totalCountArg > 0) {
                effectiveTotal = totalCountArg;
                console.log(`[NEW] updateProgressBar: Case 5 - Using totalCountArg = ${effectiveTotal} (last resort for non-zero display)`);
            }


            // Формирование текста о дедупликации и неживых ссылках
            if (sessionData.deduplication_info) {
                const dedupInfo = sessionData.deduplication_info;
                if (typeof dedupInfo.duplicates_removed === 'number' && dedupInfo.duplicates_removed > 0) {
                    deduplicationTextParts.push(`Duplicates: ${dedupInfo.duplicates_removed}`);
                }
                // Добавляем информацию о неживых ссылках
                if (typeof dedupInfo.dead_urls_removed === 'number' && dedupInfo.dead_urls_removed > 0) {
                    deduplicationTextParts.push(`Dead links: ${dedupInfo.dead_urls_removed}`);
                }
            }
        } else {
            // Если нет sessionData, используем totalCountArg, если он есть
            effectiveTotal = (typeof totalCountArg === 'number' && totalCountArg > 0) ? totalCountArg : 0;
            console.log(`[NEW] updateProgressBar: No sessionData. Using totalCountArg = ${effectiveTotal}`);
        }

        // Коррекция processedCount
        if (completed) {
            effectiveProcessed = effectiveTotal; // Если завершено, обработано = всего
        } else {
            if (effectiveProcessed > effectiveTotal && effectiveTotal > 0) { // Добавил effectiveTotal > 0 чтобы не обнулять processed, если total еще не определен
                effectiveProcessed = effectiveTotal; // Обработано не может быть больше общего
            }
        }

        // Гарантируем, что значения числовые и не отрицательные
        effectiveProcessed = Number.isFinite(effectiveProcessed) && effectiveProcessed >= 0 ? effectiveProcessed : 0;
        effectiveTotal = Number.isFinite(effectiveTotal) && effectiveTotal >= 0 ? effectiveTotal : 0;

        console.log('[NEW] updateProgressBar FINAL values:', { effectiveProcessed, effectiveTotal, completed });

        // Собираем текст о дедупликации и неживых ссылках
        const additionalInfoHtml = deduplicationTextParts.length > 0 ? `<div class="deduplication-info">${deduplicationTextParts.join(', ')}</div>` : '';

        progressStatus.style.display = 'block';
        if (!completed) {
            progressStatus.style.color = '#007bff'; // Синий для "в процессе"
            if (sessionData && sessionData.status === 'error') { // Если есть ошибка, но completed=false
                 progressStatus.style.color = 'red';
                 progressStatus.innerHTML = `Error. ${effectiveProcessed} of ${effectiveTotal} processed. ${additionalInfoHtml}`.trim();
            } else {
                 progressStatus.innerHTML = `Processing... ${effectiveProcessed} of ${effectiveTotal} processed ${additionalInfoHtml}`.trim();
            }
        } else { // completed === true
            progressStatus.style.color = 'green';
            progressStatus.innerHTML = `Completed: ${effectiveProcessed} of ${effectiveTotal} processed ${additionalInfoHtml}`.trim();
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
