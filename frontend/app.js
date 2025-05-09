document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded'); // Отладочная информация

    // DOM Elements
    const sessionSelect = document.getElementById('sessionSelect');
    const newSessionBtn = document.getElementById('newSessionBtn');
    const uploadForm = document.getElementById('uploadForm');
    const inputFile = document.getElementById('inputFile');
    const context = document.getElementById('context');
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

    console.log('Elements found:', { // Отладочная информация
        sessionSelect: !!sessionSelect,
        newSessionBtn: !!newSessionBtn,
        uploadForm: !!uploadForm,
        inputFile: !!inputFile,
        context: !!context,
        sessionControls: !!sessionControls,
        startProcessingBtn: !!startProcessingBtn,
        viewLogsBtn: !!viewLogsBtn,
        downloadResultsBtn: !!downloadResultsBtn,
        statusDisplay: !!statusDisplay,
        resultsSection: !!resultsSection,
        resultsTableBody: !!resultsTableBody,
        loadingIndicator: !!loadingIndicator,
        runBtn: !!runBtn,
        progressStatus: !!progressStatus
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
        if (sessionControls) sessionControls.style.display = 'none';
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
            if (context && context.value) {
                formData.append('context_text', context.value);
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
            showCurrentSessionUI(sessionId);
            updateStatus(`Status: ${sessionData.status}`);
            // Сохраняем ожидаемое количество компаний для прогресс-бара
            window.expectedTotalCompanies = sessionData.total_companies || sessionData.last_processed_count || 0;
            if (sessionData.status === 'completed') {
                await fetchAndDisplayResults(sessionId);
                updateProgressBar(window.expectedTotalCompanies, window.expectedTotalCompanies, true);
            }
        } catch (error) {
            console.error('Error fetching session data:', error);
            updateStatus(`Error: ${error.message}`);
        } finally {
            hideLoading();
        }
    }

    async function fetchAndDisplayResults(sessionId) {
        showLoading();
        try {
            const response = await fetch(`/api/sessions/${sessionId}/results`);
            if (!response.ok) return; // Не показываем ошибку, если результатов ещё нет
            const results = await response.json();
            displayResultsInTable(results);
            // Обновляем прогресс
            const total = window.expectedTotalCompanies || results.length;
            updateProgressBar(results.length, total, false);
            resultsSection.style.display = 'block';
            showResultsControls();
            if (progressStatus) progressStatus.style.display = 'block';
            if (newSessionBtn) newSessionBtn.style.display = 'inline-block';
        } catch (error) {
            // Не показываем тревожных сообщений, если результатов ещё нет
        } finally {
            hideLoading();
        }
    }

    function displayResultsInTable(results) {
        clearResultsTable();
        if (!results || results.length === 0) {
            resultsTableBody.innerHTML = '<tr><td colspan="4" style="text-align:center;">No results found.</td></tr>';
            return;
        }

        results.forEach(row => {
            const tr = document.createElement('tr');
            const homepage = row.homepage && row.homepage !== 'Not found' ? `<a href="${escapeHtml(row.homepage)}" target="_blank">${escapeHtml(row.homepage)}</a>` : 'Not found';
            const linkedin = row.linkedin && row.linkedin !== 'Not found' ? `<a href="${escapeHtml(row.linkedin)}" target="_blank">${escapeHtml(row.linkedin)}</a>` : 'Not found';
            tr.innerHTML = `
                <td>${escapeHtml(row.name || '')}</td>
                <td>${homepage}</td>
                <td>${linkedin}</td>
                <td>${escapeHtml(row.description || '')}</td>
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
                if (sessionData.status === 'completed') {
                    stopPollingStatus();
                    await fetchAndDisplayResults(sessionId);
                    updateProgressBar(window.expectedTotalCompanies, window.expectedTotalCompanies, true);
                } else if (sessionData.status === 'error') {
                    stopPollingStatus();
                    updateStatus(`Error: ${sessionData.error_message || 'Processing failed'}`);
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
            downloadResultsBtn.textContent = 'Download results';
            let restartBtn = document.getElementById('restartProcessingBtn');
            if (restartBtn) restartBtn.remove();
        }
    }

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
        });
    }

    if (downloadResultsBtn) {
        downloadResultsBtn.onclick = async () => {
            if (!currentSessionId) return;
            try {
                const response = await fetch(`/api/sessions/${currentSessionId}/results`);
                if (!response.ok) throw new Error('Failed to download results');
                const results = await response.json();
                const csv = convertResultsToCSV(results);
                const blob = new Blob([csv], { type: 'text/csv' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'results.csv';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch (e) {
                alert('Failed to download results');
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

    function connectWebSocket() {
        ws = new WebSocket(`ws://${window.location.host}/ws`);
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            if (data.type === "update") {
                updateTableRow(data.data);
            } else if (data.type === "complete") {
                console.log("Processing completed");
                document.getElementById("status").textContent = "Processing completed";
            }
        };
        
        ws.onclose = function() {
            console.log("WebSocket connection closed");
            // Try to reconnect after 5 seconds
            setTimeout(connectWebSocket, 5000);
        };
    }

    function updateTableRow(data) {
        if (!resultsTable) {
            resultsTable = document.getElementById("resultsTable");
        }
        
        let row = document.getElementById(`row-${data.name}`);
        if (!row) {
            // Create new row if it doesn't exist
            row = resultsTable.insertRow();
            row.id = `row-${data.name}`;
            
            // Add cells
            row.insertCell(0).textContent = data.name;
            row.insertCell(1).textContent = data.homepage;
            row.insertCell(2).textContent = data.linkedin;
            row.insertCell(3).textContent = data.description;
        } else {
            // Update existing row
            row.cells[1].textContent = data.homepage;
            row.cells[2].textContent = data.linkedin;
            row.cells[3].textContent = data.description;
        }
    }

    // Connect WebSocket when page loads
    connectWebSocket();

    // Initial load
    console.log('Starting initial load'); // Отладочная информация
}); 