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
            this.loadCriteriaPage();
        }
    }

    loadCriteriaPage() {
        const contentDiv = document.getElementById('criteria-analysis-page');
        contentDiv.style.display = 'block';
        
        // Initialize the CriteriaAnalysis logic only if it hasn't been done yet.
        if (typeof CriteriaAnalysis !== 'undefined' && !window.criteriaAnalysis) {
            window.criteriaAnalysis = new CriteriaAnalysis();
            console.log('CriteriaAnalysis initialized for the first time.');
        } else if (window.criteriaAnalysis) {
            console.log('CriteriaAnalysis already initialized, skipping re-initialization.');
            // Optionally, call a refresh method if needed when switching back to the tab
            // window.criteriaAnalysis.refreshData(); 
        }
    }
}

// Initialize router when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing router');
    window.router = new Router();
});

// Add immediate check
console.log('Router.js loaded'); 