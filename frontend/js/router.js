/**
 * Router for navigating between company generation and criteria analysis pages
 */

class Router {
    constructor() {
        this.currentPage = 'company-generation';
        this.init();
    }

    init() {
        console.log('Router init');
        // Add event listeners to navigation tabs
        const companyTab = document.getElementById('company-tab');
        const criteriaTab = document.getElementById('criteria-tab');

        console.log('Company tab:', companyTab);
        console.log('Criteria tab:', criteriaTab);

        if (companyTab) {
            companyTab.addEventListener('click', (e) => {
                e.preventDefault();
                console.log('Company tab clicked');
                this.showPage('company-generation');
            });
        }
        if (criteriaTab) {
            criteriaTab.addEventListener('click', (e) => {
                e.preventDefault();
                console.log('Criteria tab clicked');
                this.showPage('criteria-analysis');
            });
        }

        // Show default page
        this.showPage('company-generation');
    }

    async showPage(pageName) {
        console.log('Showing page:', pageName);
        this.currentPage = pageName;
        
        // Update active tab
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.classList.remove('active');
        });
        
        const activeTab = document.getElementById(`${pageName.split('-')[0]}-tab`);
        console.log('Active tab:', activeTab);
        if (activeTab) {
            activeTab.classList.add('active');
        }

        // Hide all pages
        const companyPage = document.getElementById('company-generation-page');
        const criteriaPage = document.getElementById('criteria-analysis-page');
        
        console.log('Company page:', companyPage);
        console.log('Criteria page:', criteriaPage);

        if (companyPage) companyPage.style.display = 'none';
        if (criteriaPage) criteriaPage.style.display = 'none';

        if (pageName === 'company-generation') {
            if (companyPage) companyPage.style.display = 'block';
        } else if (pageName === 'criteria-analysis') {
            await this.loadCriteriaPage();
        }
    }

    async loadCriteriaPage() {
        const contentDiv = document.getElementById('criteria-analysis-page');
        
        if (!contentDiv.innerHTML.trim()) {
            // Inline HTML content for criteria analysis
            contentDiv.innerHTML = `
            <div class="criteria-analysis-container">
                <h2>🔍 Company Criteria Analysis</h2>
                <p class="description">Analyze companies against product criteria for AI, DDOS, WAAP, CDN, and VM products.</p>
                
                <div class="info-section">
                    <h3>📋 How it works:</h3>
                    <ul>
                        <li><strong>Upload CSV/Excel</strong> with company descriptions (columns: Company_Name, Description)</li>
                        <li><strong>Algorithm analyzes</strong> each company against 5 product criteria sets</li>
                        <li><strong>Results show</strong> which companies qualify for which products/audiences</li>
                        <li><strong>Download CSV</strong> with detailed qualification results</li>
                    </ul>
                </div>

                <div class="products-info">
                    <h3>🎯 Product Categories:</h3>
                    <div class="product-tags">
                        <span class="product-tag ai">AI</span>
                        <span class="product-tag ddos">DDOS Protection</span>
                        <span class="product-tag waap">WAAP Security</span>
                        <span class="product-tag cdn">CDN Services</span>
                        <span class="product-tag vm">VM Solutions</span>
                    </div>
                </div>
                
                <div class="upload-section">
                    <h3>📤 Upload Company Data</h3>
                    <form id="criteria-upload-form" enctype="multipart/form-data">
                        <div class="form-group">
                            <label for="criteria-file">Select CSV/Excel file with company descriptions:</label>
                            <input type="file" id="criteria-file" name="file" accept=".csv,.xlsx,.xls" required>
                            <small>Required columns: Company_Name, Description (or similar)</small>
                        </div>
                        
                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="load-all-companies" name="load_all_companies">
                                Also load all files from data/ folder
                            </label>
                        </div>
                        
                        <button type="submit" class="analyze-btn">🚀 Analyze Companies</button>
                    </form>
                </div>

                <div id="criteria-status" class="status-section" style="display: none;">
                    <h3>⏳ Analysis Status</h3>
                    <div class="status-info">
                        <p><strong>Session ID:</strong> <span id="criteria-session-id"></span></p>
                        <p><strong>Status:</strong> <span id="criteria-status-text"></span></p>
                        <div id="criteria-progress" class="progress-bar" style="display: none;">
                            <div class="progress-fill"></div>
                        </div>
                    </div>
                    
                    <div class="action-buttons">
                        <button id="cancel-criteria-btn" style="display: none;">❌ Cancel</button>
                        <button id="refresh-criteria-btn">🔄 Refresh</button>
                    </div>
                </div>

                <div id="criteria-results" class="results-section" style="display: none;">
                    <h3>📊 Analysis Results</h3>
                    <div class="results-summary">
                        <p><strong>Companies Analyzed:</strong> <span id="results-count"></span></p>
                        <button id="download-results-btn-router" class="download-btn">💾 Download Full Results</button>
                    </div>
                    
                    <div class="results-table-container">
                        <h4>🔍 Results Preview (first 10 rows):</h4>
                        <div id="results-table"></div>
                    </div>
                </div>

                <div id="criteria-sessions-list" class="sessions-section">
                    <h3>📜 Recent Sessions</h3>
                    <button id="load-sessions-btn">📋 Load History</button>
                    <div id="sessions-container"></div>
                </div>
            </div>
            
            <style>
                .criteria-analysis-container {
                    max-width: 1000px;
                    margin: 0 auto;
                    padding: 20px;
                }
                
                .description {
                    font-size: 16px;
                    color: #666;
                    margin-bottom: 25px;
                    line-height: 1.5;
                }
                
                .info-section {
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 25px;
                }
                
                .info-section ul {
                    margin: 10px 0 0 20px;
                }
                
                .info-section li {
                    margin-bottom: 8px;
                    line-height: 1.4;
                }
                
                .products-info {
                    margin-bottom: 25px;
                }
                
                .product-tags {
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                    margin-top: 10px;
                }
                
                .product-tag {
                    padding: 6px 12px;
                    border-radius: 15px;
                    font-size: 14px;
                    font-weight: 500;
                    color: white;
                }
                
                .product-tag.ai { background: #6f42c1; }
                .product-tag.ddos { background: #dc3545; }
                .product-tag.waap { background: #fd7e14; }
                .product-tag.cdn { background: #20c997; }
                .product-tag.vm { background: #0d6efd; }
                
                .upload-section {
                    background: white;
                    border: 2px dashed #007bff;
                    border-radius: 8px;
                    padding: 25px;
                    margin-bottom: 25px;
                }
                
                .analyze-btn {
                    background: linear-gradient(135deg, #007bff, #0056b3);
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                }
                
                .analyze-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 8px rgba(0,123,255,0.3);
                }
                
                .download-btn {
                    background: linear-gradient(135deg, #28a745, #20c997);
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 6px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                }
                
                .download-btn:hover {
                    transform: translateY(-1px);
                    box-shadow: 0 3px 6px rgba(40,167,69,0.3);
                }
                
                .status-section, .results-section, .sessions-section {
                    background: #f8f9fa;
                    border-radius: 8px;
                    padding: 20px;
                    margin-bottom: 20px;
                }
                
                .action-buttons {
                    margin-top: 15px;
                    display: flex;
                    gap: 10px;
                }
                
                .results-table {
                    overflow-x: auto;
                    margin-top: 15px;
                }
                
                .results-table table {
                    width: 100%;
                    border-collapse: collapse;
                    background: white;
                    border-radius: 6px;
                    overflow: hidden;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                
                .results-table th {
                    background: #007bff;
                    color: white;
                    padding: 12px;
                    text-align: left;
                }
                
                .results-table td {
                    padding: 10px 12px;
                    border-bottom: 1px solid #eee;
                }
                
                .results-table tr:hover {
                    background: #f8f9fa;
                }
                
                .progress-bar {
                    width: 100%;
                    height: 8px;
                    background: #e9ecef;
                    border-radius: 4px;
                    overflow: hidden;
                    margin: 10px 0;
                }
                
                .progress-fill {
                    height: 100%;
                    background: linear-gradient(90deg, #007bff, #0056b3);
                    animation: progress-animation 2s ease-in-out infinite;
                }
                
                @keyframes progress-animation {
                    0% { width: 0%; }
                    50% { width: 70%; }
                    100% { width: 100%; }
                }
                
                .session-item {
                    background: white;
                    border-radius: 6px;
                    padding: 15px;
                    margin-bottom: 10px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                
                .session-info {
                    display: flex;
                    flex-direction: column;
                    gap: 5px;
                }
                
                .status.completed { color: #28a745; font-weight: 600; }
                .status.processing { color: #007bff; font-weight: 600; }
                .status.failed { color: #dc3545; font-weight: 600; }
                
                small {
                    color: #6c757d;
                    font-size: 12px;
                }
            </style>
            `;
            
            // Load criteria analysis script
            if (!document.getElementById('criteria-analysis-script')) {
                const script = document.createElement('script');
                script.id = 'criteria-analysis-script';
                script.src = '/static/js/criteria-analysis.js';
                script.onload = () => {
                    // Initialize criteria analysis after script loads
                    if (window.CriteriaAnalysis) {
                        window.criteriaAnalysis = new window.CriteriaAnalysis();
                    }
                };
                document.head.appendChild(script);
            }
        }
        
        contentDiv.style.display = 'block';
    }
}

// Initialize router when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing router');
    window.router = new Router();
});

// Add immediate check
console.log('Router.js loaded'); 