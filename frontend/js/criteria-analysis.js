/**
 * JavaScript для страницы анализа критериев
 */

class CriteriaAnalysis {
    constructor() {
        this.currentSessionId = null;
        this.statusCheckInterval = null;
        this.criteriaFiles = [];
        this.selectedCriteria = [];
        this.currentEditingFile = null;
        this.criteriaData = null;
        this.init();
    }

    init() {
        this.bindEvents();
        // Автоматически загружаем список файлов критериев для боковой панели
        this.loadCriteriaFiles();
    }

    bindEvents() {
        // Ensure we're properly referencing the button on this page
        const analyzeBtn = document.getElementById('criteria-analyze-btn');
        const uploadForm = document.getElementById('criteria-upload-form');
        const cancelBtn = document.getElementById('cancel-criteria-btn');
        const refreshBtn = document.getElementById('refresh-criteria-btn');
        
        // Download buttons (there are multiple ones due to different pages/structures)
        const downloadBtn = document.getElementById('download-results-btn');
        const downloadBtnMain = document.getElementById('download-results-btn-main');
        const downloadBtnRouter = document.getElementById('download-results-btn-router');
        
        console.log('Binding events for criteria analysis:', {
            analyzeBtn: !!analyzeBtn,
            uploadForm: !!uploadForm,
            cancelBtn: !!cancelBtn,
            refreshBtn: !!refreshBtn,
            downloadBtn: !!downloadBtn,
            downloadBtnMain: !!downloadBtnMain,
            downloadBtnRouter: !!downloadBtnRouter
        });

        if (uploadForm) {
            uploadForm.addEventListener('submit', (e) => this.handleUpload(e));
        }

        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.cancelAnalysis());
        }

        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.checkStatus());
        }

        // Add event listeners to all download buttons (to handle different page structures)
        [downloadBtn, downloadBtnMain, downloadBtnRouter].forEach(btn => {
            if (btn && !btn.dataset.bound) {
                btn.addEventListener('click', () => this.downloadResults());
                btn.dataset.bound = 'true'; // Prevent multiple bindings
            }
        });

        // Bind load sessions button
        const loadSessionsBtn = document.getElementById('load-sessions-btn');
        if (loadSessionsBtn) {
            loadSessionsBtn.addEventListener('click', () => this.loadSessions());
        }

        // Bind criteria file management
        const refreshCriteriaBtn = document.getElementById('refresh-criteria-btn');
        if (refreshCriteriaBtn) {
            refreshCriteriaBtn.addEventListener('click', () => this.loadCriteriaFiles());
        }

        // Bind criteria editor buttons
        const saveCriteriaBtn = document.getElementById('save-criteria-btn');
        const cancelEditBtn = document.getElementById('cancel-edit-btn');
        const addRowBtn = document.getElementById('add-row-btn');
        const deleteRowBtn = document.getElementById('delete-row-btn');

        if (saveCriteriaBtn) {
            saveCriteriaBtn.addEventListener('click', () => this.saveCriteriaFile());
        }
        if (cancelEditBtn) {
            cancelEditBtn.addEventListener('click', () => this.cancelEdit());
        }
        if (addRowBtn) {
            addRowBtn.addEventListener('click', () => this.addTableRow());
        }
        if (deleteRowBtn) {
            deleteRowBtn.addEventListener('click', () => this.deleteSelectedRows());
        }

        // Setup drag & drop for company files
        this.setupCompanyDragDrop();
    }

    setupCompanyDragDrop() {
        const dropZoneContainer = document.getElementById('criteria-dropZoneContainer');
        const inputFile = document.getElementById('criteria-file');
        const customChooseFileButton = document.getElementById('criteria-customChooseFileButton');
        const fileNameDisplay = document.getElementById('criteria-fileNameDisplay');

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
                    console.log('Company file(s) dropped and assigned to input:', files);
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
    }

    async handleUpload(event) {
        event.preventDefault();
        
        const formData = new FormData();
        const fileInput = document.getElementById('criteria-file');
        const loadAllCheckbox = document.getElementById('load-all-companies');
        
        if (!fileInput.files[0]) {
            alert('Please select a file');
            return;
        }

        formData.append('file', fileInput.files[0]);
        formData.append('load_all_companies', loadAllCheckbox ? loadAllCheckbox.checked : false);

        // Disable analyze button during processing
        const analyzeBtn = document.getElementById('criteria-analyze-btn');
        if (analyzeBtn) {
            analyzeBtn.disabled = true;
            analyzeBtn.textContent = '⏳ Analyzing...';
        }

        try {
            this.showStatus('Uploading file...');
            
            const response = await fetch('/api/criteria/analyze', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            
            if (!response.ok) {
                throw new Error(result.detail || 'Upload error');
            }

            this.currentSessionId = result.session_id;
            document.getElementById('criteria-session-id').textContent = this.currentSessionId;
            
                        this.showStatus('Analysis started...');
            this.resetResultsPanel();
            this.startStatusChecking();

        } catch (error) {
            console.error('Upload error:', error);
            this.showStatus(`Error: ${error.message}`, 'error');
            
            // Re-enable analyze button on error
            const analyzeBtn = document.getElementById('criteria-analyze-btn');
            if (analyzeBtn) {
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = ' Analyze ';
            }
        }
    }

    showStatus(message, type = 'info') {
        const statusSection = document.getElementById('criteria-status');
        const statusText = document.getElementById('criteria-status-text');
        const progressBar = document.getElementById('criteria-progress');
        const cancelBtn = document.getElementById('cancel-criteria-btn');
        const downloadBtn = document.getElementById('download-results-btn-main') || 
                           document.getElementById('download-results-btn-router');
        const analyzeBtn = document.getElementById('criteria-analyze-btn');

        statusSection.style.display = 'block';
        statusText.textContent = message;
        statusText.className = type;

        if (type === 'processing') {
            progressBar.style.display = 'block';
            cancelBtn.style.display = 'inline-block';
            if (downloadBtn) downloadBtn.style.display = 'none';
            // Keep analyze button disabled during processing
            if (analyzeBtn) {
                analyzeBtn.disabled = true;
                analyzeBtn.textContent = '⏳ Analyzing...';
            }
        } else if (type === 'completed' || message.includes('завершен') || message.includes('completed')) {
            progressBar.style.display = 'none';
            cancelBtn.style.display = 'none';
            if (downloadBtn) downloadBtn.style.display = 'inline-block';
            // Re-enable analyze button when completed
            if (analyzeBtn) {
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = ' Analyze ';
            }
        } else {
            progressBar.style.display = 'none';
            cancelBtn.style.display = 'none';
            if (downloadBtn) downloadBtn.style.display = 'none';
            // Re-enable analyze button on error or other states
            if (analyzeBtn) {
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = ' Analyze ';
            }
        }
    }

    startStatusChecking() {
        this.statusCheckInterval = setInterval(() => {
            this.checkStatus();
        }, 10000); // Check every 10 seconds
    }

    stopStatusChecking() {
        if (this.statusCheckInterval) {
            clearInterval(this.statusCheckInterval);
            this.statusCheckInterval = null;
        }
    }

    async checkStatus() {
        if (!this.currentSessionId) return;

        try {
            const response = await fetch(`/api/criteria/sessions/${this.currentSessionId}/status`);
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Status check error');
            }

            const status = result.status;
            this.showStatus(this.getStatusMessage(status), this.getStatusType(status));

            if (status === 'completed') {
                this.stopStatusChecking();
                this.loadResults();
            } else if (status === 'failed' || status === 'cancelled') {
                this.stopStatusChecking();
            }

        } catch (error) {
            console.error('Status check error:', error);
        }
    }

    getStatusMessage(status) {
        const messages = {
            'created': 'Session created',
            'processing': 'Analysis in progress...',
            'completed': 'Analysis completed successfully',
            'failed': 'Analysis failed',
            'cancelled': 'Analysis cancelled'
        };
        return messages[status] || status;
    }

    getStatusType(status) {
        if (status === 'processing') return 'processing';
        if (status === 'completed') return 'success';
        if (status === 'failed') return 'error';
        return 'info';
    }

    async loadResults() {
        if (!this.currentSessionId) return;

        try {
            const response = await fetch(`/api/criteria/sessions/${this.currentSessionId}/results`);
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Results loading error');
            }

            this.displayResults(result);

        } catch (error) {
            console.error('Results loading error:', error);
            this.showStatus(`Results loading error: ${error.message}`, 'error');
        }
    }

    displayResults(result) {
        const resultsSection = document.getElementById('criteria-results');
        const resultsTable = document.getElementById('results-table');
        const placeholder = document.getElementById('no-results-placeholder');

        // Hide placeholder and show results panel
        if (placeholder) placeholder.style.display = 'none';
        resultsSection.style.display = 'flex';

        if (result.results && result.results.length > 0) {
            this.createResultsTable(result.results, resultsTable);
        } else {
            resultsTable.innerHTML = '<p>No data to display</p>';
        }
    }

    createResultsTable(data, container) {
        if (!data || data.length === 0) {
            container.innerHTML = '<p>No data to display</p>';
            return;
        }

        // Параметры пагинации
        const itemsPerPage = 20;
        const totalPages = Math.ceil(data.length / itemsPerPage);
        let currentPage = 1;

        // Колонки для отображения
        const columnsToShow = [
            { key: 'Company_Name', label: 'Company' },
            { key: 'Description', label: 'Description' },
            { key: 'Product', label: 'Product' },
            { key: 'All_Results', label: 'All Results' },
            { key: 'Qualified_Products', label: 'Qualified Products' }
        ];

        // Функция для создания таблицы
        const renderTable = (pageNumber) => {
            const startIndex = (pageNumber - 1) * itemsPerPage;
            const endIndex = Math.min(startIndex + itemsPerPage, data.length);
            const pageData = data.slice(startIndex, endIndex);

            // Очищаем контейнер
            const tableContainer = document.createElement('div');
            tableContainer.className = 'table-container';

            const table = document.createElement('table');
            table.className = 'results-table';
            table.style.width = '100%';
            table.style.borderCollapse = 'collapse';

            // Создаем заголовок
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            
            columnsToShow.forEach(column => {
                const th = document.createElement('th');
                th.textContent = column.label;
                th.style.padding = '12px';
                th.style.textAlign = 'left';
                th.style.borderBottom = '1px solid #ddd';
                th.style.backgroundColor = '#f8f9fa';
                th.style.fontWeight = 'bold';
                th.style.verticalAlign = 'top';
                headerRow.appendChild(th);
            });
            
            thead.appendChild(headerRow);
            table.appendChild(thead);

            // Создаем тело таблицы
            const tbody = document.createElement('tbody');
            pageData.forEach(row => {
                const tr = document.createElement('tr');
                tr.style.borderBottom = '1px solid #ddd';
                
                columnsToShow.forEach(column => {
                    const td = document.createElement('td');
                    td.style.padding = '12px';
                    td.style.verticalAlign = 'top';
                    td.style.borderBottom = '1px solid #ddd';
                    
                    if (column.key === 'Company_Name') {
                        this.renderCompanyCell(td, row);
                    } else {
                        this.renderDataCell(td, row[column.key], column.key);
                    }
                    
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
            
            table.appendChild(tbody);
            tableContainer.appendChild(table);

            // Добавляем информацию о пагинации
            const paginationInfo = document.createElement('div');
            paginationInfo.style.display = 'flex';
            paginationInfo.style.justifyContent = 'space-between';
            paginationInfo.style.alignItems = 'center';
            paginationInfo.style.marginTop = '15px';
            paginationInfo.style.padding = '10px 0';

            const info = document.createElement('span');
            info.textContent = `Showing ${startIndex + 1}-${endIndex} of ${data.length} records`;
            info.style.color = '#666';
            info.style.fontSize = '14px';

            const paginationControls = document.createElement('div');
            paginationControls.style.display = 'flex';
            paginationControls.style.gap = '5px';

            // Кнопка "Предыдущая"
            const prevBtn = document.createElement('button');
            prevBtn.textContent = '← Previous';
            prevBtn.disabled = currentPage === 1;
            prevBtn.style.padding = '5px 10px';
            prevBtn.style.fontSize = '12px';
            prevBtn.onclick = () => {
                if (currentPage > 1) {
                    currentPage--;
                    renderTable(currentPage);
                }
            };

            // Номера страниц (показываем только некоторые)
            const startPage = Math.max(1, currentPage - 2);
            const endPage = Math.min(totalPages, currentPage + 2);

            for (let i = startPage; i <= endPage; i++) {
                const pageBtn = document.createElement('button');
                pageBtn.textContent = i;
                pageBtn.style.padding = '5px 8px';
                pageBtn.style.fontSize = '12px';
                if (i === currentPage) {
                    pageBtn.style.backgroundColor = '#007bff';
                    pageBtn.style.color = 'white';
                    pageBtn.disabled = true;
                }
                pageBtn.onclick = () => {
                    currentPage = i;
                    renderTable(currentPage);
                };
                paginationControls.appendChild(pageBtn);
            }

            // Кнопка "Следующая"
            const nextBtn = document.createElement('button');
            nextBtn.textContent = 'Next →';
            nextBtn.disabled = currentPage === totalPages;
            nextBtn.style.padding = '5px 10px';
            nextBtn.style.fontSize = '12px';
            nextBtn.onclick = () => {
                if (currentPage < totalPages) {
                    currentPage++;
                    renderTable(currentPage);
                }
            };

            paginationControls.appendChild(prevBtn);
            paginationControls.appendChild(nextBtn);

            paginationInfo.appendChild(info);
            paginationInfo.appendChild(paginationControls);

            tableContainer.appendChild(paginationInfo);

            // Заменяем содержимое контейнера
            container.innerHTML = '';
            container.appendChild(tableContainer);
        };

        // Рендерим первую страницу
        renderTable(1);
    }

    renderCompanyCell(td, row) {
        const companyName = row['Company_Name'] || '';
        const website = row['Official_Website'] || '';
        const linkedin = row['LinkedIn_URL'] || '';
        
        // Создаем название компании жирным
        const nameDiv = document.createElement('div');
        nameDiv.style.fontWeight = 'bold';
        nameDiv.style.marginBottom = '4px';
        nameDiv.textContent = companyName;
        td.appendChild(nameDiv);
        
        // Добавляем ссылку на сайт
        if (website) {
            const websiteDiv = document.createElement('div');
            websiteDiv.style.fontSize = '12px';
            websiteDiv.style.marginBottom = '2px';
            
            const websiteLink = document.createElement('a');
            websiteLink.href = website.startsWith('http') ? website : `https://${website}`;
            websiteLink.target = '_blank';
            websiteLink.rel = 'noopener noreferrer';
            websiteLink.style.color = '#007bff';
            websiteLink.style.textDecoration = 'none';
            websiteLink.style.fontSize = '12px';
            websiteLink.textContent = '🌐 Website';
            
            websiteLink.addEventListener('mouseover', () => {
                websiteLink.style.textDecoration = 'underline';
            });
            websiteLink.addEventListener('mouseout', () => {
                websiteLink.style.textDecoration = 'none';
            });
            
            websiteDiv.appendChild(websiteLink);
            td.appendChild(websiteDiv);
        }
        
        // Добавляем ссылку на LinkedIn
        if (linkedin) {
            const linkedinDiv = document.createElement('div');
            linkedinDiv.style.fontSize = '12px';
            
            const linkedinLink = document.createElement('a');
            linkedinLink.href = linkedin;
            linkedinLink.target = '_blank';
            linkedinLink.rel = 'noopener noreferrer';
            linkedinLink.style.color = '#0077b5';
            linkedinLink.style.textDecoration = 'none';
            linkedinLink.style.fontSize = '12px';
            linkedinLink.textContent = '🔗 LinkedIn';
            
            linkedinLink.addEventListener('mouseover', () => {
                linkedinLink.style.textDecoration = 'underline';
            });
            linkedinLink.addEventListener('mouseout', () => {
                linkedinLink.style.textDecoration = 'none';
            });
            
            linkedinDiv.appendChild(linkedinLink);
            td.appendChild(linkedinDiv);
        }
    }

    renderDataCell(td, value, columnKey) {
        if (columnKey === 'All_Results' && typeof value === 'object') {
            // Форматируем JSON с переносами строк
            td.textContent = JSON.stringify(value, null, 2);
            td.style.fontFamily = 'monospace';
            td.style.fontSize = '12px';
            td.style.whiteSpace = 'pre-wrap';
        } else if (columnKey === 'Qualified_Products' && value) {
            // Форматируем текст с переносами строк
            const content = value.toString().replace(/\\n/g, '\n');
            td.textContent = content;
            td.style.whiteSpace = 'pre-wrap';
            td.style.fontSize = '13px';
        } else if (typeof value === 'object') {
            // Другие JSON объекты
            td.textContent = JSON.stringify(value, null, 2);
            td.style.fontFamily = 'monospace';
            td.style.fontSize = '12px';
            td.style.whiteSpace = 'pre-wrap';
        } else {
            td.textContent = value || '';
            if (columnKey === 'Description') {
                td.style.maxWidth = '400px';
                td.style.whiteSpace = 'pre-wrap';
                td.style.wordWrap = 'break-word';
            }
        }
    }

    async cancelAnalysis() {
        if (!this.currentSessionId) return;

        try {
            const response = await fetch(`/api/criteria/sessions/${this.currentSessionId}/cancel`, {
                method: 'POST'
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Cancellation error');
            }

            this.stopStatusChecking();
            this.showStatus('Analysis cancelled', 'info');

        } catch (error) {
            console.error('Cancel error:', error);
            this.showStatus(`Cancellation error: ${error.message}`, 'error');
        }
    }

    async downloadResults() {
        if (!this.currentSessionId) return;

        try {
            const response = await fetch(`/api/criteria/sessions/${this.currentSessionId}/download`);

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Download error');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `criteria_analysis_${this.currentSessionId}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

        } catch (error) {
            console.error('Download error:', error);
            alert(`Download error: ${error.message}`);
        }
    }

    resetResultsPanel() {
        const resultsSection = document.getElementById('criteria-results');
        const placeholder = document.getElementById('no-results-placeholder');
        
        // Hide results and show placeholder
        resultsSection.style.display = 'none';
        if (placeholder) placeholder.style.display = 'flex';
    }

    async loadSessions() {
        try {
            const response = await fetch('/api/criteria/sessions');
            const sessions = await response.json();

            if (!response.ok) {
                throw new Error('Sessions loading error');
            }

            this.displaySessions(sessions);

        } catch (error) {
            console.error('Sessions loading error:', error);
        }
    }

    displaySessions(sessions) {
        const container = document.getElementById('sessions-container');
        
        // Если контейнер не найден, игнорируем вывод сессий
        if (!container) {
            console.log('Sessions container not found, skipping sessions display');
            return;
        }
        
        if (!sessions || sessions.length === 0) {
            container.innerHTML = '<p>No available sessions</p>';
            return;
        }

        const sessionsList = document.createElement('div');
        sessionsList.className = 'sessions-list';

        sessions.slice(0, 5).forEach(session => {
            const sessionDiv = document.createElement('div');
            sessionDiv.className = 'session-item';
            sessionDiv.innerHTML = `
                <div class="session-info">
                    <strong>${session.session_id}</strong>
                    <span class="status ${session.status}">${this.getStatusMessage(session.status)}</span>
                    <small>${new Date(session.created_time).toLocaleString()}</small>
                </div>
                <button onclick="criteriaAnalysis.loadSession('${session.session_id}')" 
                        ${session.status !== 'completed' ? 'disabled' : ''}>
                    Load
                </button>
            `;
            sessionsList.appendChild(sessionDiv);
        });

        container.innerHTML = '';
        container.appendChild(sessionsList);
    }

    async loadSession(sessionId) {
        this.currentSessionId = sessionId;
        document.getElementById('criteria-session-id').textContent = sessionId;
        
        await this.checkStatus();
        if (document.getElementById('criteria-status-text').textContent.includes('завершен')) {
            this.loadResults();
        }
    }

    // === CRITERIA MANAGEMENT METHODS ===

    async loadCriteriaFiles() {
        try {
            const response = await fetch('/api/criteria/files');
            const result = await response.json();

            if (!response.ok) {
                throw new Error('Failed to load criteria files');
            }

            this.criteriaFiles = result.files;
            
            // Автоматически выбираем все файлы критериев по умолчанию
            this.selectedCriteria = this.criteriaFiles.map(file => file.filename);
            
            this.displayCriteriaFiles();

        } catch (error) {
            console.error('Error loading criteria files:', error);
            this.displayCriteriaError('Failed to load criteria files');
        }
    }

    displayCriteriaFiles() {
        const container = document.getElementById('criteria-files-list');
        
        if (!this.criteriaFiles || this.criteriaFiles.length === 0) {
            container.innerHTML = '<p style="color: #6c757d;">No criteria files found</p>';
            return;
        }

        const filesList = document.createElement('div');
        filesList.style.cssText = 'display: grid; gap: 10px;';

        this.criteriaFiles.forEach(file => {
            const fileItem = document.createElement('div');
            fileItem.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 10px; background: white; border: 1px solid #ddd; border-radius: 4px;';
            
            const isSelected = this.selectedCriteria.includes(file.filename);
            if (isSelected) {
                fileItem.style.backgroundColor = '#e3f2fd';
                fileItem.style.borderColor = '#2196f3';
            }

            fileItem.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px;">
                    <input type="checkbox" ${isSelected ? 'checked' : ''} 
                           onchange="criteriaAnalysis.toggleCriteriaSelection('${file.filename}', this.checked)">
                    <div>
                        <strong>${file.filename}</strong>
                        <br>                        <small style="color: #6c757d;">
                            ${file.total_rows || 0} rows | Modified: ${new Date(file.modified).toLocaleDateString()}
                        </small>
                        ${file.error ? `<br><small style="color: #dc3545;">Error: ${file.error}</small>` : ''}
                    </div>
                </div>
                <div style="display: flex; gap: 5px;">
                    <button onclick="criteriaAnalysis.editCriteriaFile('${file.filename}')" 
                            style="background: #007bff; color: white; border: none; padding: 4px 8px; border-radius: 3px; cursor: pointer; font-size: 12px;">
                        ✏️ Edit
                    </button>
                    <button onclick="criteriaAnalysis.deleteCriteriaFile('${file.filename}')" 
                            style="background: #dc3545; color: white; border: none; padding: 4px 8px; border-radius: 3px; cursor: pointer; font-size: 12px;">
                        🗑️ Delete
                    </button>
                </div>
            `;

            filesList.appendChild(fileItem);
        });

        container.innerHTML = '';
        container.appendChild(filesList);
        
        this.updateSelectedCriteriaDisplay();
    }

    displayCriteriaError(message) {
        const container = document.getElementById('criteria-files-list');
        container.innerHTML = `<p style="color: #dc3545;">Error: ${message}</p>`;
    }

    toggleCriteriaSelection(filename, selected) {
        if (selected) {
            if (!this.selectedCriteria.includes(filename)) {
                this.selectedCriteria.push(filename);
            }
        } else {
            const index = this.selectedCriteria.indexOf(filename);
            if (index > -1) {
                this.selectedCriteria.splice(index, 1);
            }
        }
        
        this.displayCriteriaFiles(); // Refresh display
        this.updateSelectedCriteriaDisplay();
    }

    updateSelectedCriteriaDisplay() {
        const container = document.getElementById('selected-criteria-display');
        const listContainer = document.getElementById('selected-criteria-list');
        
        if (this.selectedCriteria.length > 0) {
            container.style.display = 'block';
            listContainer.innerHTML = this.selectedCriteria.map(filename => 
                `<span style="display: inline-block; background: #007bff; color: white; padding: 2px 8px; border-radius: 10px; margin: 2px; font-size: 12px;">${filename}</span>`
            ).join('');
        } else {
            container.style.display = 'none';
        }
    }

    async editCriteriaFile(filename) {
        try {
            const response = await fetch(`/api/criteria/files/${filename}`);
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Failed to load file');
            }

            this.currentEditingFile = filename;
            this.criteriaData = result;
            this.showCriteriaEditor();

        } catch (error) {
            console.error('Error loading criteria file:', error);
            alert(`Error loading file: ${error.message}`);
        }
    }

    showCriteriaEditor() {
        const editor = document.getElementById('criteria-editor');
        const title = document.getElementById('editor-title');
        const tableContainer = document.getElementById('criteria-table-container');

        title.textContent = `Edit: ${this.currentEditingFile}`;
        editor.style.display = 'block';

        // Create editable table
        this.createEditableTable(tableContainer);
        
        // Scroll to editor
        editor.scrollIntoView({ behavior: 'smooth' });
    }

    createEditableTable(container) {
        const table = document.createElement('table');
        table.style.cssText = 'width: 100%; border-collapse: collapse; background: white;';
        table.id = 'criteria-edit-table';

        // Create header
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        
        // Add checkbox column for row selection
        const checkboxHeader = document.createElement('th');
        checkboxHeader.style.cssText = 'padding: 8px; background: #f8f9fa; border: 1px solid #ddd; width: 30px;';
        checkboxHeader.innerHTML = '<input type="checkbox" onchange="criteriaAnalysis.toggleAllRows(this.checked)">';
        headerRow.appendChild(checkboxHeader);

        this.criteriaData.columns.forEach(column => {
            const th = document.createElement('th');
            th.style.cssText = 'padding: 8px; background: #f8f9fa; border: 1px solid #ddd; min-width: 120px;';
            th.textContent = column;
            headerRow.appendChild(th);
        });

        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Create body
        const tbody = document.createElement('tbody');
        this.criteriaData.data.forEach((row, rowIndex) => {
            const tr = document.createElement('tr');
            tr.dataset.rowIndex = rowIndex;

            // Add checkbox for row selection
            const checkboxCell = document.createElement('td');
            checkboxCell.style.cssText = 'padding: 8px; border: 1px solid #ddd; text-align: center;';
            checkboxCell.innerHTML = `<input type="checkbox" class="row-checkbox">`;
            tr.appendChild(checkboxCell);

            this.criteriaData.columns.forEach(column => {
                const td = document.createElement('td');
                td.style.cssText = 'padding: 8px; border: 1px solid #ddd;';
                td.contentEditable = true;
                td.textContent = row[column] || '';
                td.dataset.column = column;
                tr.appendChild(td);
            });

            tbody.appendChild(tr);
        });

        table.appendChild(tbody);
        container.innerHTML = '';
        container.appendChild(table);
    }

    toggleAllRows(checked) {
        const checkboxes = document.querySelectorAll('.row-checkbox');
        checkboxes.forEach(checkbox => {
            checkbox.checked = checked;
        });
    }

    addTableRow() {
        const table = document.getElementById('criteria-edit-table');
        const tbody = table.querySelector('tbody');
        
        const newRow = document.createElement('tr');
        newRow.dataset.rowIndex = tbody.children.length;

        // Add checkbox
        const checkboxCell = document.createElement('td');
        checkboxCell.style.cssText = 'padding: 8px; border: 1px solid #ddd; text-align: center;';
        checkboxCell.innerHTML = `<input type="checkbox" class="row-checkbox">`;
        newRow.appendChild(checkboxCell);

        // Add empty cells for each column
        this.criteriaData.columns.forEach(column => {
            const td = document.createElement('td');
            td.style.cssText = 'padding: 8px; border: 1px solid #ddd;';
            td.contentEditable = true;
            td.textContent = '';
            td.dataset.column = column;
            newRow.appendChild(td);
        });

        tbody.appendChild(newRow);
    }

    deleteSelectedRows() {
        const selectedCheckboxes = document.querySelectorAll('.row-checkbox:checked');
        
        if (selectedCheckboxes.length === 0) {
            alert('No rows selected for deletion');
            return;
        }

        if (!confirm(`Delete ${selectedCheckboxes.length} selected row(s)?`)) {
            return;
        }

        // Remove rows in reverse order to maintain indices
        const rowsToDelete = Array.from(selectedCheckboxes)
            .map(checkbox => checkbox.closest('tr'))
            .sort((a, b) => parseInt(b.dataset.rowIndex) - parseInt(a.dataset.rowIndex));

        rowsToDelete.forEach(row => row.remove());
    }

    async saveCriteriaFile() {
        if (!this.currentEditingFile) return;

        try {
            // Collect data from table
            const table = document.getElementById('criteria-edit-table');
            const rows = table.querySelectorAll('tbody tr');
            
            const data = [];
            rows.forEach(row => {
                const rowData = {};
                this.criteriaData.columns.forEach(column => {
                    const cell = row.querySelector(`td[data-column="${column}"]`);
                    rowData[column] = cell ? cell.textContent.trim() : '';
                });
                data.push(rowData);
            });

            const payload = {
                columns: this.criteriaData.columns,
                data: data
            };

            const response = await fetch(`/api/criteria/files/${this.currentEditingFile}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Failed to save file');
            }

            alert(`File saved successfully! ${result.rows_saved} rows saved.`);
            this.cancelEdit();
            this.loadCriteriaFiles(); // Refresh file list

        } catch (error) {
            console.error('Error saving criteria file:', error);
            alert(`Error saving file: ${error.message}`);
        }
    }

    cancelEdit() {
        const editor = document.getElementById('criteria-editor');
        editor.style.display = 'none';
        this.currentEditingFile = null;
        this.criteriaData = null;
    }

    async deleteCriteriaFile(filename) {
        if (!confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/criteria/files/${filename}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Failed to delete file');
            }

            alert(`File deleted successfully. Backup created at: ${result.backup_location}`);
            
            // Remove from selected criteria if it was selected
            const index = this.selectedCriteria.indexOf(filename);
            if (index > -1) {
                this.selectedCriteria.splice(index, 1);
            }
            
            this.loadCriteriaFiles(); // Refresh file list

        } catch (error) {
            console.error('Error deleting criteria file:', error);
            alert(`Error deleting file: ${error.message}`);
        }
    }

    async uploadCriteriaFile(file) {
        try {
            // Validate file type
            if (!file.name.endsWith('.csv')) {
                alert('Only CSV files are supported for criteria upload.');
                return;
            }

            const formData = new FormData();
            formData.append('filename', file.name);
            
            // Read file content
            const fileContent = await this.readFileAsText(file);
            const lines = fileContent.split('\n').filter(line => line.trim());
            
            if (lines.length < 2) {
                alert('File must have at least 2 lines (header + data).');
                return;
            }

            // Parse CSV
            const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
            const data = [];
            
            for (let i = 1; i < lines.length; i++) {
                const values = lines[i].split(',').map(v => v.trim().replace(/"/g, ''));
                if (values.length === headers.length) {
                    const row = {};
                    headers.forEach((header, index) => {
                        row[header] = values[index] || '';
                    });
                    data.push(row);
                }
            }

            const payload = {
                filename: file.name,
                columns: headers,
                data: data
            };

            const response = await fetch('/api/criteria/files', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Failed to upload criteria file');
            }

            alert(`Criteria file uploaded successfully: ${result.filename}`);
            this.loadCriteriaFiles(); // Refresh file list

        } catch (error) {
            console.error('Error uploading criteria file:', error);
            alert(`Error uploading file: ${error.message}`);
        }
    }

    readFileAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = reject;
            reader.readAsText(file);
        });
    }
}

// Global function for HTML drag & drop handler
function handleCriteriaFileDrop(event) {
    event.preventDefault();
    
    const files = event.dataTransfer.files;
    if (files.length === 0) return;
    
    if (window.criteriaAnalysis) {
        for (let file of files) {
            window.criteriaAnalysis.uploadCriteriaFile(file);
        }
    }
}

// Make class available globally
window.CriteriaAnalysis = CriteriaAnalysis;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if we're on the criteria analysis page AND not already initialized
    if (document.getElementById('criteria-upload-form') && !window.criteriaAnalysis) {
        console.log('Initializing CriteriaAnalysis...');
        window.criteriaAnalysis = new CriteriaAnalysis();
    }
}); 