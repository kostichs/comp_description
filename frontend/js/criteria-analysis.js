/**
 * JavaScript для страницы анализа критериев
 */

class CriteriaAnalysis {
    constructor() {
        this.currentSessionId = null;
        this.statusCheckInterval = null;
        this.criteriaFiles = [];
        this.availableProducts = [];
        this.selectedCriteria = [];  // Now stores selected product names
        this.currentEditingFile = null;
        this.criteriaData = null;
        this.init();
    }

    init() {
        this.bindEvents();
        // Автоматически загружаем список файлов критериев для боковой панели
        this.loadCriteriaFiles().then(() => {
            // Принудительное обновление чекбоксов при инициализации
            console.log('🔄 Initial forced refresh of checkboxes');
            this.displayCriteriaFiles();
        });
        this.initLatestSessionCheckbox();
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
            uploadForm.addEventListener('submit', (e) => {
                // МГНОВЕННО отключаем кнопку ПЕРВЫМ ДЕЛОМ
                const analyzeBtn = document.getElementById('criteria-analyze-btn');
                if (analyzeBtn) {
                    analyzeBtn.disabled = true;
                    analyzeBtn.textContent = '⏳ Analyzing...';
                }
                
                this.handleUploadWithSessionCheck(e);
            });
        }

        // Также привязываем обработчик напрямую к кнопке для дополнительной гарантии
        if (analyzeBtn) {
            console.log('Binding analyze button directly');
            analyzeBtn.addEventListener('click', (e) => {
                // Если кнопка submit в форме, предотвращаем двойное срабатывание
                if (analyzeBtn.type === 'submit') {
                    // Store checkbox state before disabling everything
                    const deepAnalysisCheckbox = document.getElementById('deep-analysis-checkbox');
                    if (deepAnalysisCheckbox) {
                        deepAnalysisCheckbox.dataset.waschecked = deepAnalysisCheckbox.checked;
                    }
                    return; // Пусть срабатывает через форму
                }
                this.handleUploadWithSessionCheck(e);
            });
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

        // Use event delegation on the parent container for the dynamic button
        const statusContainer = document.getElementById('criteria-status');
        if (statusContainer) {
            statusContainer.addEventListener('click', (event) => {
                if (event.target && event.target.id === 'download-scrapingbee-logs-btn') {
                    this.downloadScrapingBeeLogs();
                }
            });
        }

        // Bind load sessions button
        const loadSessionsBtn = document.getElementById('load-sessions-btn');
        if (loadSessionsBtn) {
            loadSessionsBtn.addEventListener('click', () => this.loadSessions());
        }

        // Bind criteria file management
        const refreshCriteriaBtn = document.getElementById('refresh-criteria-btn');
        if (refreshCriteriaBtn) {
            refreshCriteriaBtn.addEventListener('click', async () => {
                console.log('🔄 Refresh button clicked - FORCED update of all components');
                await this.loadCriteriaFiles();
                this.displayCriteriaFiles();
                console.log('✅ Forced refresh completed');
            });
        }

        // Bind refresh status button
        const refreshStatusBtn = document.getElementById('refresh-status-btn');
        if (refreshStatusBtn) {
            refreshStatusBtn.addEventListener('click', () => this.checkStatus());
        }

        // Обработчик для кнопки "Новая сессия"
        const newSessionBtn = document.getElementById('new-session-btn');
        if (newSessionBtn) {
            newSessionBtn.addEventListener('click', () => this.startNewSession());
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
        
        // Setup drag & drop for criteria files
        this.setupCriteriaDragDrop();
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

    setupCriteriaDragDrop() {
        const criteriaDropZone = document.getElementById('criteria-drop-zone');
        
        if (!criteriaDropZone) {
            console.error('Criteria drop zone not found!');
            return;
        }
        
        console.log('Setting up criteria drag & drop handlers');
        
        criteriaDropZone.addEventListener('dragover', (event) => {
            event.preventDefault();
            criteriaDropZone.style.backgroundColor = '#e8f5e8';
            criteriaDropZone.style.borderColor = '#20c997';
        });
        
        criteriaDropZone.addEventListener('dragleave', (event) => {
            criteriaDropZone.style.backgroundColor = '#f8fff8';
            criteriaDropZone.style.borderColor = '#28a745';
        });
        
        criteriaDropZone.addEventListener('drop', (event) => {
            console.log('Drop event on criteria zone!');
            event.preventDefault();
            criteriaDropZone.style.backgroundColor = '#f8fff8';
            criteriaDropZone.style.borderColor = '#28a745';
            
            // Process dropped files
            this.handleCriteriaFileDrop(event);
        });
    }

    handleCriteriaFileDrop(event) {
        console.log(' handleCriteriaFileDrop called from class method!');
        
        const files = event.dataTransfer.files;
        console.log('Files dropped:', files.length);
        
        if (files.length === 0) {
            console.log('No files in drop event');
            return;
        }
        
        // Log file details
        for (let i = 0; i < files.length; i++) {
            console.log(` File ${i + 1}: ${files[i].name} (${files[i].size} bytes, type: ${files[i].type})`);
        }
        
        // Process all files sequentially  
        const processFiles = async () => {
            for (let file of files) {
                console.log(`Processing file: ${file.name}`);
                await this.uploadCriteriaFile(file);
            }
            
            // После загрузки всех файлов, полностью обновляем интерфейс
            console.log(' All criteria files uploaded, refreshing complete interface');
            await this.loadCriteriaFiles();
            
            // МГНОВЕННОЕ обновление чекбоксов продуктов
            console.log(' Force refreshing product checkboxes...');
            this.displayCriteriaFiles(); // Принудительно перерисовываем чекбоксы
        };
        
        processFiles().catch(error => {
            console.error(' Error processing dropped criteria files:', error);
            alert(`Error processing files: ${error.message}`);
        });
    }

    async handleUpload(event) {
        event.preventDefault();
        
        const formData = new FormData();
        const fileInput = document.getElementById('criteria-file');
        const loadAllCheckbox = document.getElementById('load-all-companies');
        const useDeepAnalysis = document.getElementById('deep-analysis-checkbox').checked;
        
        // Skip file validation if using latest session
        const useLatestSession = document.getElementById('use-latest-session').checked;
        if (!useLatestSession && !fileInput.files[0]) {
            alert('Please select a file');
            return;
        }

        formData.append('file', fileInput.files[0]);
        formData.append('load_all_companies', loadAllCheckbox ? loadAllCheckbox.checked : false);
        formData.append('use_deep_analysis', useDeepAnalysis);
        // Отправляем выбранные файлы критериев вместо продуктов
        formData.append('selected_criteria_files', JSON.stringify(this.selectedCriteria));

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
            throw error; // Пропускаем ошибку выше для обработки в handleUploadWithSessionCheck
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
        
        // Use the parent container of the download button
        const downloadButtonsContainer = downloadBtn ? downloadBtn.parentElement : null;

        // Remove existing scrapingbee button to avoid duplicates
        const existingScrapingBtn = document.getElementById('download-scrapingbee-logs-btn');
        if (existingScrapingBtn) {
            existingScrapingBtn.remove();
        }

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
                analyzeBtn.textContent = ' Analyzing...';
            }
        } else if (type === 'completed' || message.includes('завершен') || message.includes('completed')) {
            progressBar.style.display = 'none';
            cancelBtn.style.display = 'none';
            if (downloadBtn) downloadBtn.style.display = 'inline-block';
            
            // Check if deep analysis was used to show the button
            const deepAnalysisCheckbox = document.getElementById('deep-analysis-checkbox');
            if (deepAnalysisCheckbox && (deepAnalysisCheckbox.checked || deepAnalysisCheckbox.dataset.waschecked === 'true') && downloadButtonsContainer) {
                // Ensure we don't add duplicates
                if (!document.getElementById('download-scrapingbee-logs-btn')) {
                    const scrapingBeeBtn = document.createElement('button');
                    scrapingBeeBtn.id = 'download-scrapingbee-logs-btn';
                    // Apply similar styling as the main download button
                    scrapingBeeBtn.className = 'btn btn-secondary';
                    scrapingBeeBtn.textContent = 'Download Logs';
                    scrapingBeeBtn.style.marginLeft = '10px';
                    scrapingBeeBtn.style.background = '#6c757d';
                    
                    downloadButtonsContainer.appendChild(scrapingBeeBtn);
                }
            }

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
        if (!this.currentSessionId) {
            console.log('No session ID for status check');
            return;
        }

        try {
            // Используем новый эндпоинт для детального прогресса
            const response = await fetch(`/api/criteria/sessions/${this.currentSessionId}/progress`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Status check failed');
            }

            console.log('Progress data:', data);

            // Обновляем прогресс бар с процентом
            this.updateProgressBar(data.percentage || 0);
            
            // Создаем детальное сообщение о прогрессе
            let statusMessage = data.message || 'Processing...';
            
            if (data.detailed_progress && data.progress) {
                // Добавляем детальную информацию о критериях
                if (data.progress.criteria && data.progress.criteria !== "0/0") {
                    statusMessage += `\n Criteria: ${data.progress.criteria}`;
                }
                
                // Добавляем информацию о компаниях
                if (data.progress.companies && data.progress.companies !== "0/0") {
                    statusMessage += `\n Companies: ${data.progress.companies}`;
                }
                
                // Добавляем breakdown по типам критериев
                if (data.criteria_summary) {
                    statusMessage += `\n ${data.criteria_summary}`;
                }
                
                // Добавляем текущую информацию
                if (data.current && data.current.company && data.current.product) {
                    statusMessage += `\n Processing: ${data.current.company} → ${data.current.product}`;
                }
                
                // Добавляем информацию об аудитории
                if (data.current && data.current.audience) {
                    statusMessage += ` (${data.current.audience})`;
                }
            }

            if (data.status === 'processing') {
                this.showStatus(statusMessage, 'processing');
                // Продолжаем проверять статус
                setTimeout(() => this.checkStatus(), 3000); // Проверяем каждые 3 секунды
            } else if (data.status === 'completed') {
                this.showStatus('Analysis completed successfully!', 'completed');
                this.updateProgressBar(100);
                this.stopStatusChecking();
                // Автоматически загружаем результаты при завершении
                setTimeout(() => this.loadResults(), 1000);
            } else if (data.status === 'failed') {
                const errorMsg = data.error || 'Analysis failed';
                this.showStatus(`Analysis failed: ${errorMsg}`, 'error');
                this.updateProgressBar(0);
                this.stopStatusChecking();
            } else if (data.status === 'cancelled') {
                this.showStatus('Analysis cancelled', 'error');
                this.updateProgressBar(0);
                this.stopStatusChecking();
            } else {
                this.showStatus(`Status: ${data.status}`, 'info');
            }

        } catch (error) {
            console.error('Status check error:', error);
            // Fallback to simple status check
            try {
                const fallbackResponse = await fetch(`/api/criteria/sessions/${this.currentSessionId}/status`);
                const fallbackData = await fallbackResponse.json();
                
                if (fallbackResponse.ok) {
                    this.showStatus(this.getStatusMessage(fallbackData.status), 
                                  fallbackData.status === 'processing' ? 'processing' : 'info');
                    
                    if (fallbackData.status === 'processing') {
                        setTimeout(() => this.checkStatus(), 5000);
                    } else {
                        this.stopStatusChecking();
                    }
                } else {
                    this.showStatus(`Status check failed: ${error.message}`, 'error');
                }
            } catch (fallbackError) {
                this.showStatus(`Status check failed: ${error.message}`, 'error');
                this.stopStatusChecking();
            }
        }
    }

    updateProgressBar(percentage) {
        const progressBar = document.querySelector('#criteria-progress div');
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.style.transition = 'width 0.3s ease';
            
            // Добавляем текст с процентами
            if (percentage > 0) {
                progressBar.textContent = `${percentage}%`;
                progressBar.style.textAlign = 'center';
                progressBar.style.lineHeight = '20px';
                progressBar.style.color = 'white';
                progressBar.style.fontSize = '12px';
                progressBar.style.fontWeight = 'bold';
            }
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

    async startNewSession() {
        // Подтверждение от пользователя
        const confirmed = confirm('Вы уверены что хотите начать новую сессию? Текущий анализ будет остановлен.');
        if (!confirmed) {
            return;
        }

        try {
            // Отменяем текущую сессию если она есть
            if (this.currentSessionId) {
                console.log('Cancelling current session:', this.currentSessionId);
                
                const cancelResponse = await fetch(`/api/criteria/sessions/${this.currentSessionId}/cancel`, {
                    method: 'POST'
                });

                if (cancelResponse.ok) {
                    console.log('Current session cancelled successfully');
                } else {
                    console.warn('Failed to cancel current session, but continuing with reset');
                }
            }

            // Останавливаем все активные процессы
            this.stopStatusChecking();

            // Сбрасываем состояние интерфейса
            this.resetInterface();

            // Показываем успешное сообщение
            this.showStatus('Session was successfully reset', 'success');
            
        } catch (error) {
            console.error('Error starting new session:', error);
            this.showStatus(`Ошибка при создании новой сессии: ${error.message}`, 'error');
        }
    }

    resetInterface() {
        // Сбрасываем текущую сессию
        this.currentSessionId = null;
        
        // Очищаем все элементы статуса
        document.getElementById('criteria-session-id').textContent = '';
        document.getElementById('criteria-status-text').textContent = '';
        
        // Скрываем секцию статуса
        const statusSection = document.getElementById('criteria-status');
        if (statusSection) {
            statusSection.style.display = 'none';
        }
        
        // Сбрасываем прогресс бар
        const progressBar = document.getElementById('criteria-progress');
        if (progressBar) {
            progressBar.style.display = 'none';
            const progressFill = progressBar.querySelector('div');
            if (progressFill) {
                progressFill.style.width = '0%';
            }
        }
        
        // Скрываем кнопки отмены и загрузки
        const cancelBtn = document.getElementById('cancel-criteria-btn');
        if (cancelBtn) cancelBtn.style.display = 'none';
        
        const downloadBtn = document.getElementById('download-results-btn-main');
        if (downloadBtn) downloadBtn.style.display = 'none';
        
        // Сбрасываем панель результатов
        this.resetResultsPanel();
        
        // Очищаем форму загрузки файла
        const fileInput = document.getElementById('criteria-file');
        if (fileInput) {
            fileInput.value = '';
        }
        
        const fileNameDisplay = document.getElementById('criteria-fileNameDisplay');
        if (fileNameDisplay) {
            fileNameDisplay.textContent = '';
        }
        
        // Перезагружаем файлы критериев для обновления состояния
        this.loadCriteriaFiles();
        
        console.log('Interface reset completed');
    }

    async downloadResults() {
        const sessionId = document.getElementById('criteria-session-id').textContent;
        if (!sessionId) {
            alert('Session ID not found on the page. Cannot download results.');
            return;
        }

        try {
            const response = await fetch(`/api/criteria/sessions/${sessionId}/download`);

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Download error');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `criteria_analysis_${sessionId}.csv`;
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

            console.log(' loadCriteriaFiles: API response received');
            console.log('📁 Files count:', result.files ? result.files.length : 0);

            this.criteriaFiles = result.files;
            this.availableProducts = result.products || []; // Сохраняем для совместимости
            
            // Сохраняем предыдущие выборы файлов если они были
            const previouslySelected = [...this.selectedCriteria];
            console.log(' Previously selected files:', previouslySelected);
            
            // Умная логика выбора файлов
            if (previouslySelected.length > 0) {
                // Сохраняем предыдущий выбор + добавляем новые файлы
                const currentFilenames = this.criteriaFiles.map(f => f.filename);
                const newFiles = currentFilenames.filter(f => !previouslySelected.includes(f));
                this.selectedCriteria = [...previouslySelected.filter(f => currentFilenames.includes(f)), ...newFiles];
            } else {
                // Автоматически выбираем все файлы по умолчанию (первый запуск)
                this.selectedCriteria = this.criteriaFiles.map(f => f.filename);
            }
            
            console.log(' Final selected files:', this.selectedCriteria);
            
            this.displayCriteriaFiles();

        } catch (error) {
            console.error('Error loading criteria files:', error);
            this.displayCriteriaError('Failed to load criteria files');
        }
    }

    displayCriteriaFiles() {
        const container = document.getElementById('criteria-files-list');
        
        // ПРИНУДИТЕЛЬНАЯ ОЧИСТКА контейнера
        container.innerHTML = '';
        
        console.log(' displayCriteriaFiles called');
        console.log('   Available files:', this.criteriaFiles.length);
        console.log('   Selected criteria:', this.selectedCriteria);
        
        if (!this.criteriaFiles || this.criteriaFiles.length === 0) {
            container.innerHTML = '<p style="color: #6c757d;">No criteria files found</p>';
            return;
        }

        // Отображаем файлы критериев С ЧЕКБОКСАМИ для выбора
        const filesList = document.createElement('div');
        filesList.style.cssText = 'display: grid; gap: 10px;';
        
        const filesTitle = document.createElement('h4');
        filesTitle.textContent = 'Select Criteria Files to Use:';
        filesTitle.style.cssText = 'margin: 0 0 15px 0; color: #333;';
        filesList.appendChild(filesTitle);

        this.criteriaFiles.forEach(file => {
            console.log(`   Creating file item for: ${file.filename}`);
            
            const fileItem = document.createElement('div');
            fileItem.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 10px; background: white; border: 1px solid #ddd; border-radius: 4px;';

            // Проверяем выбран ли этот файл (по имени файла)
            const isSelected = this.selectedCriteria.includes(file.filename);
            console.log(`      File ${file.filename} selected: ${isSelected}`);
            
            if (isSelected) {
                fileItem.style.backgroundColor = '#e3f2fd';
                fileItem.style.borderColor = '#2196f3';
            }

            // Левая часть с чекбоксом и информацией о файле
            const leftPart = document.createElement('div');
            leftPart.style.cssText = 'display: flex; align-items: center; flex: 1;';
            
            // Создаем чекбокс для выбора файла
            const checkboxId = `file-checkbox-${file.filename.replace(/[^a-zA-Z0-9]/g, '_')}`;
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = checkboxId;
            checkbox.checked = isSelected;
            checkbox.style.cssText = 'margin-right: 12px; transform: scale(1.2);';
            
            // ПРАВИЛЬНЫЙ биндинг события для файла
            checkbox.addEventListener('change', (e) => {
                console.log(`File checkbox changed for ${file.filename}: ${e.target.checked}`);
                this.toggleFileSelection(file.filename, e.target.checked);
            });
            
            // Информация о файле
            const fileInfo = document.createElement('div');
            fileInfo.innerHTML = `
                <strong>${file.filename}</strong>
                <br>
                <small style="color: #6c757d;">
                    ${file.total_rows || 0} rows | Modified: ${new Date(file.modified).toLocaleDateString()}
                </small>
                ${file.products && file.products.length > 0 ? 
                    `<br><small style="color: #007bff;">Products: ${file.products.join(', ')}</small>` : ''}
                ${file.error ? `<br><small style="color: #dc3545;">Error: ${file.error}</small>` : ''}
            `;
            
            leftPart.appendChild(checkbox);
            leftPart.appendChild(fileInfo);
            
            // Правая часть с кнопками управления
            const rightPart = document.createElement('div');
            rightPart.style.cssText = 'display: flex; gap: 5px; margin-left: 10px;';
            rightPart.innerHTML = `
                <button onclick="criteriaAnalysis.editCriteriaFile('${file.filename}')" 
                        style="background: #007bff; color: white; border: none; padding: 4px 8px; border-radius: 3px; cursor: pointer; font-size: 12px;">
                    Edit
                </button>
                <button onclick="criteriaAnalysis.deleteCriteriaFile('${file.filename}')" 
                        style="background: #dc3545; color: white; border: none; padding: 4px 8px; border-radius: 3px; cursor: pointer; font-size: 12px;">
                    Delete
                </button>
            `;

            fileItem.appendChild(leftPart);
            fileItem.appendChild(rightPart);
            filesList.appendChild(fileItem);
        });

        // ПРИНУДИТЕЛЬНОЕ добавление в DOM
        container.appendChild(filesList);
        
        console.log(' displayCriteriaFiles completed, DOM updated');
        
        this.updateSelectedCriteriaDisplay();
    }

    displayCriteriaError(message) {
        const container = document.getElementById('criteria-files-list');
        container.innerHTML = `<p style="color: #dc3545;">Error: ${message}</p>`;
    }

    toggleFileSelection(filename, selected) {
        console.log('=== DEBUG: toggleFileSelection ===');
        console.log('filename:', filename);
        console.log('selected:', selected);
        console.log('Before change - this.selectedCriteria:', this.selectedCriteria);
        
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
        
        console.log('After change - this.selectedCriteria:', this.selectedCriteria);
        
        this.displayCriteriaFiles(); // Refresh display
        this.updateSelectedCriteriaDisplay();
    }

    updateSelectedCriteriaDisplay() {
        // Обновляем отображение в sidebar (основной список файлов для выбора)
        const sidebarContainer = document.getElementById('selected-criteria-display');
        const sidebarListContainer = document.getElementById('selected-criteria-list');
        
        if (sidebarContainer && sidebarListContainer) {
            if (this.selectedCriteria.length > 0) {
                sidebarContainer.style.display = 'block';
                sidebarListContainer.innerHTML = this.selectedCriteria.map(filename => 
                    `<span style="display: inline-block; background: #007bff; color: white; padding: 2px 8px; border-radius: 10px; margin: 2px; font-size: 12px;">${filename}</span>`
                ).join('');
            } else {
                sidebarContainer.style.display = 'none';
            }
        }
        
        // Обновляем отображение в форме (дополнительный display)
        const formContainer = document.getElementById('selected-products-display');
        const formListContainer = document.getElementById('selected-products-list');
        
        if (formContainer && formListContainer) {
            if (this.selectedCriteria.length > 0) {
                formContainer.style.display = 'block';
                formContainer.querySelector('strong').textContent = 'Selected Files:'; // Меняем заголовок
                formListContainer.innerHTML = this.selectedCriteria.map(filename => 
                    `<span style="display: inline-block; background: #007bff; color: white; padding: 2px 8px; border-radius: 10px; margin: 2px; font-size: 12px;">${filename}</span>`
                ).join('');
            } else {
                formContainer.style.display = 'none';
            }
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
            await this.loadCriteriaFiles(); // Refresh file list and products
            
            // МГНОВЕННОЕ обновление чекбоксов продуктов
            this.displayCriteriaFiles();

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

            alert(`File deleted successfully`);
            
            // Reload criteria files to update available products
            await this.loadCriteriaFiles();
            
            // МГНОВЕННОЕ обновление чекбоксов продуктов
            this.displayCriteriaFiles();

        } catch (error) {
            console.error('Error deleting criteria file:', error);
            alert(`Error deleting file: ${error.message}`);
        }
    }

    async uploadCriteriaFile(file) {
        console.log(`🔄 uploadCriteriaFile started for: ${file.name}`);
        try {
            // Validate file type
            if (!file.name.endsWith('.csv') && !file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
                console.log('❌ File validation failed: not a supported file type');
                alert('Only CSV and Excel files are supported for criteria upload.');
                return;
            }
            console.log('✅ File validation passed: supported file type');

            const formData = new FormData();
            formData.append('file', file);
            
            console.log(`📤 Sending POST request to /api/criteria/upload for ${file.name}`);

            const response = await fetch('/api/criteria/upload', {
                method: 'POST',
                body: formData
            });
            
            console.log(`📥 Response status: ${response.status} ${response.statusText}`);

            const result = await response.json();

            if (!response.ok) {
                console.log(` Server error: ${result.detail || 'Unknown error'}`);
                throw new Error(result.detail || 'Failed to upload criteria file');
            }

            console.log(` Upload successful: ${result.filename}`);
            alert(`Criteria file uploaded successfully: ${result.filename}`);
            
            // МГНОВЕННОЕ обновление после загрузки КАЖДОГО файла
            console.log(' INSTANT refresh after file upload...');
            await this.loadCriteriaFiles();
            this.displayCriteriaFiles();

        } catch (error) {
            console.error(' Error uploading criteria file:', error);
            alert(`Error uploading file: ${error.message}`);
        }
    }

    parseCSV(text) {
        const result = [];
        const lines = text.split('\n');
        
        for (let line of lines) {
            line = line.trim();
            if (!line) continue;
            
            const row = [];
            let current = '';
            let inQuotes = false;
            
            for (let i = 0; i < line.length; i++) {
                const char = line[i];
                
                if (char === '"') {
                    if (inQuotes && line[i + 1] === '"') {
                        // Handle escaped quotes
                        current += '"';
                        i++; // Skip next quote
                    } else {
                        // Toggle quote state
                        inQuotes = !inQuotes;
                    }
                } else if (char === ',' && !inQuotes) {
                    // Field separator
                    row.push(current.trim());
                    current = '';
                } else {
                    current += char;
                }
            }
            
            // Add the last field
            row.push(current.trim());
            result.push(row);
        }
        
        return result;
    }

    readFileAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = reject;
            reader.readAsText(file);
        });
    }

    initLatestSessionCheckbox() {
        const checkbox = document.getElementById('use-latest-session');
        const dropZoneContainer = document.getElementById('criteria-dropZoneContainer');
        const fileInput = document.getElementById('criteria-file');
        
        if (checkbox && dropZoneContainer && fileInput) {
            checkbox.addEventListener('change', () => {
                this.toggleLatestSessionMode(checkbox.checked);
            });
            
            // Загружаем информацию о последней сессии
            this.loadLatestSessionInfo();
        }
    }

    async loadLatestSessionInfo() {
        try {
            const response = await fetch('/api/sessions');
            const sessions = await response.json();
            
            if (!response.ok) {
                throw new Error('Failed to fetch sessions');
            }

            // Найти последнюю завершенную сессию
            const completedSessions = sessions.filter(s => s.status === 'completed');
            
            const latestSessionInfoEl = document.getElementById('latest-session-info');
            const checkbox = document.getElementById('use-latest-session');
            
            if (completedSessions.length > 0) {
                const latestSession = completedSessions[0]; // Уже отсортированы по времени создания
                const sessionDate = new Date(latestSession.created_time).toLocaleString();
                const companiesCount = latestSession.total_companies || 0;
                
                latestSessionInfoEl.textContent = `Latest session: ${latestSession.session_id} (${sessionDate}, ${companiesCount} companies)`;
                latestSessionInfoEl.style.display = 'block';
                checkbox.style.display = 'inline-block';
                checkbox.disabled = false;
                
                this.latestSessionId = latestSession.session_id;
                
                console.log('🔄 Latest session info updated:', latestSession.session_id);
            } else {
                latestSessionInfoEl.textContent = 'No completed sessions found';
                latestSessionInfoEl.style.display = 'block';
                checkbox.disabled = true;
                checkbox.style.display = 'none';
                this.latestSessionId = null;
            }
        } catch (error) {
            console.error('Error loading latest session info:', error);
            const latestSessionInfoEl = document.getElementById('latest-session-info');
            latestSessionInfoEl.textContent = 'Error loading session information';
            latestSessionInfoEl.style.display = 'block';
        }
    }
    
    // Глобальная функция для обновления из других компонентов
    refreshLatestSessionInfo() {
        console.log('🔄 Refreshing latest session info from external trigger');
        // Небольшая задержка чтобы сервер успел обновить метаданные сессии
        setTimeout(() => {
            this.loadLatestSessionInfo();
        }, 1000);
    }

    toggleLatestSessionMode(useLatestSession) {
        const dropZoneContainer = document.getElementById('criteria-dropZoneContainer');
        const fileInput = document.getElementById('criteria-file');
        const fileNameDisplay = document.getElementById('criteria-fileNameDisplay');
        
        if (useLatestSession) {
            // Отключаем drag-and-drop и файловый input
            dropZoneContainer.style.opacity = '0.5';
            dropZoneContainer.style.pointerEvents = 'none';
            fileInput.disabled = true;
            fileNameDisplay.textContent = 'Using results from latest session';
            fileNameDisplay.style.color = '#007bff';
        } else {
            // Включаем drag-and-drop и файловый input обратно
            dropZoneContainer.style.opacity = '1';
            dropZoneContainer.style.pointerEvents = 'auto';
            fileInput.disabled = false;
            fileNameDisplay.textContent = '';
        }
    }

    async handleUploadWithSessionCheck(event) {
        event.preventDefault();
        
        const useLatestSession = document.getElementById('use-latest-session').checked;
        const fileInput = document.getElementById('criteria-file');
        const hasFile = fileInput && fileInput.files && fileInput.files.length > 0;
        
        // Проверяем условия - если плохо, включаем кнопку обратно
        if (!useLatestSession && !hasFile) {
            const analyzeBtn = document.getElementById('criteria-analyze-btn');
            if (analyzeBtn) {
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = ' Analyze ';
            }
            alert('Please select a file or check "Use results from latest session" checkbox');
            return;
        }
        
        try {
            if (useLatestSession) {
                return await this.handleUploadFromSession();
            } else {
                return await this.handleUpload(event);
            }
        } catch (error) {
            // При ошибке возвращаем кнопку обратно
            if (analyzeBtn) {
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = ' Analyze ';
            }
            throw error;
        }
    }

    async handleUploadFromSession() {
        if (!this.latestSessionId) {
            alert('No latest session available');
            return;
        }

        // Debug logging
        console.log('=== DEBUG: handleUploadFromSession ===');
        console.log('this.selectedCriteria:', this.selectedCriteria);
        console.log('this.availableProducts:', this.availableProducts);
        console.log('JSON.stringify(this.selectedCriteria):', JSON.stringify(this.selectedCriteria));

        const formData = new FormData();
        const loadAllCheckbox = document.getElementById('load-all-companies');
        const useDeepAnalysis = document.getElementById('deep-analysis-checkbox').checked;
        
        formData.append('session_id', this.latestSessionId);
        formData.append('load_all_companies', loadAllCheckbox ? loadAllCheckbox.checked : false);
        formData.append('use_deep_analysis', useDeepAnalysis);
        formData.append('selected_criteria_files', JSON.stringify(this.selectedCriteria));

        // Debug: Show what's in FormData
        console.log('FormData contents:');
        for (let [key, value] of formData.entries()) {
            console.log(`${key}:`, value);
        }

        try {
            this.showStatus('Using results from latest session...');
            
            const response = await fetch('/api/criteria/analyze_from_session', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            
            if (!response.ok) {
                throw new Error(result.detail || 'Analysis error');
            }

            this.currentSessionId = result.session_id;
            document.getElementById('criteria-session-id').textContent = this.currentSessionId;
            
            this.showStatus('Analysis started...');
            this.resetResultsPanel();
            this.startStatusChecking();

        } catch (error) {
            console.error('Upload from session error:', error);
            this.showStatus(`Error: ${error.message}`, 'error');
            throw error; // Пропускаем ошибку выше для обработки в handleUploadWithSessionCheck
        }
    }

    async downloadScrapingBeeLogs() {
        const sessionId = document.getElementById('criteria-session-id').textContent;
        if (!sessionId) {
            alert('Session ID not found on the page. Cannot download logs.');
            return;
        }

        try {
            console.log(`Downloading ScrapingBee logs for session: ${sessionId}`);
            const response = await fetch(`/api/criteria/sessions/${sessionId}/scrapingbee_logs`);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `scrapingbee_logs_${sessionId}.log`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();

        } catch (error) {
            console.error('Error downloading ScrapingBee logs:', error);
            alert(`Failed to download logs: ${error.message}`);
        }
    }
}

// Global function removed - now using class method setupCriteriaDragDrop()

// Make class available globally
window.CriteriaAnalysis = CriteriaAnalysis;

// Глобальная функция для обновления информации о последней сессии (для вызова из других компонентов)
window.refreshLatestSessionInfo = function() {
    if (window.criteriaAnalysis && typeof window.criteriaAnalysis.refreshLatestSessionInfo === 'function') {
        console.log('🔄 Global trigger: refreshing latest session info...');
        window.criteriaAnalysis.refreshLatestSessionInfo();
    } else {
        console.log('⚠️ CriteriaAnalysis not initialized yet');
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize if we're on the criteria analysis page AND not already initialized
    if (document.getElementById('criteria-upload-form') && !window.criteriaAnalysis) {
        console.log('Initializing CriteriaAnalysis...');
        window.criteriaAnalysis = new CriteriaAnalysis();
    }
}); 