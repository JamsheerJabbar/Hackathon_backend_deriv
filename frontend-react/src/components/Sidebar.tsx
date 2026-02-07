import { API_BASE_URL } from '../config';
import './Sidebar.css';

const DOMAINS = [
    { id: 'general', label: 'General', icon: '🌐' },
    { id: 'security', label: 'Security', icon: '🔒' },
    { id: 'compliance', label: 'Compliance', icon: '📋' },
    { id: 'risk', label: 'Risk', icon: '⚠️' },
    { id: 'operations', label: 'Operations', icon: '⚙️' },
];

const EXAMPLE_QUERIES = [
    'Show me all high severity incidents',
    'What are the compliance violations in the last 30 days?',
    'List all open security risks',
    'Show operational metrics for last quarter',
];

interface SidebarProps {
    mode: string;
    setMode: (mode: string) => void;
    selectedDomain: string;
    setSelectedDomain: (domain: string) => void;
    onOpenHistory?: () => void;
}

export default function Sidebar({ mode, setMode, selectedDomain, setSelectedDomain, onOpenHistory }: SidebarProps) {
    return (
        <aside className="sidebar">
            {/* Mode Toggle */}
            <div className="sidebar-section">
                <button
                    className={`mode-toggle-btn ${mode === 'sentinel' ? 'active' : ''}`}
                    onClick={() => setMode(mode === 'sentinel' ? 'chat' : 'sentinel')}
                >
                    <span className="pulse-ring"></span>
                    <span className="icon">{mode === 'sentinel' ? '💬' : '🛰️'}</span>
                    {mode === 'sentinel' ? 'QUERY CHAT' : 'SENTINEL MODE'}
                </button>
            </div>

            {/* Scan History (sentinel mode only) */}
            {mode === 'sentinel' && onOpenHistory && (
                <div className="sidebar-section">
                    <button className="history-btn" onClick={onOpenHistory}>
                        <span className="icon">📋</span>
                        Scan History
                    </button>
                </div>
            )}

            {/* Domain Selection */}
            {mode === 'chat' && (
                <div className="sidebar-section">
                    <h3>Domain Selection</h3>
                    <div className="domain-selector">
                        {DOMAINS.map((domain) => (
                            <button
                                key={domain.id}
                                className={`domain-btn ${selectedDomain === domain.id ? 'active' : ''}`}
                                onClick={() => setSelectedDomain(domain.id)}
                            >
                                <span className="domain-icon">{domain.icon}</span>
                                {domain.label}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Quick Examples */}
            {mode === 'chat' && (
                <div className="sidebar-section">
                    <h3>Quick Examples</h3>
                    <div className="examples-list">
                        {EXAMPLE_QUERIES.map((query, idx) => (
                            <div key={idx} className="example-item">
                                <span className="example-icon">💡</span>
                                {query}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* API Configuration */}
            <div className="sidebar-section">
                <h3>API Configuration</h3>
                <div className="api-config">
                    <label htmlFor="api-url">API Endpoint</label>
                    <input
                        type="text"
                        id="api-url"
                        defaultValue={API_BASE_URL}
                        readOnly
                    />
                </div>
            </div>
        </aside>
    );
}
