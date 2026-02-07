import { useState, useEffect, useRef, useCallback } from 'react';
import { Bar, Line } from 'react-chartjs-2';
import ReactMarkdown from 'react-markdown';
import { API_BASE_URL } from '../config';
import './SentinelDashboard.css';

// ─── Types ──────────────────────────────────────────────────────────────────

interface RiskFactor {
    value: number | string;
    score: number;
    detail: string;
}

interface MissionLog {
    ts: number;
    level: string;
    node: string;
    msg: string;
}

interface Detection {
    mission_id: string;
    mission_name: string;
    domain: string;
    severity: string;
    risk_score: number;
    risk_factors: Record<string, RiskFactor>;
    sql: string;
    data_count: number;
    results?: any[];
    visualization_config?: any;
    insight?: string;
    recommendation?: string | string[];
    timestamp: string;
    depth?: number;
    parent_mission_id?: string | null;
    rationale?: string;
    error?: string;
    logs?: MissionLog[];
}

interface ThreatCluster {
    cluster_id: string;
    threat_name: string;
    severity: string;
    connected_missions: string[];
    shared_entities: {
        user_ids?: string[];
        countries?: string[];
        ip_addresses?: string[];
    };
    narrative: string;
    recommended_action: string;
}

interface Narrative {
    title: string;
    overall_risk: number;
    overall_severity: string;
    executive_summary: string;
    threat_vectors: { name: string; severity: string; description: string }[];
    immediate_actions: string[];
    monitoring_recommendations: string[];
}

interface MissionPlan {
    id: string;
    name: string;
    domain: string;
}

export interface HistoricalScan {
    scan_id: string;
    timestamp: string;
    detections: Detection[];
    clusters: ThreatCluster[];
    narrative: Narrative | null;
    stats: {
        total_missions: number;
        critical_count: number;
        overall_risk: number;
        overall_severity: string;
    };
}

interface SentinelDashboardProps {
    historicalScan?: HistoricalScan | null;
    onBackToLive?: () => void;
}

// Polling interval in milliseconds
const POLL_INTERVAL = 3000;

// ─── Component ──────────────────────────────────────────────────────────────

export default function SentinelDashboard({ historicalScan, onBackToLive }: SentinelDashboardProps) {
    const [detections, setDetections] = useState<Detection[]>([]);
    const [clusters, setClusters] = useState<ThreatCluster[]>([]);
    const [narrative, setNarrative] = useState<Narrative | null>(null);
    const [missionPlan, setMissionPlan] = useState<MissionPlan[]>([]);
    const [scanCount, setScanCount] = useState(0);
    const [phase, setPhase] = useState<string>('idle');
    const [progress, setProgress] = useState({ completed: 0, total: 0 });
    const [adaptiveContext, setAdaptiveContext] = useState<any>(null);
    const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set());
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const stopPolling = useCallback(() => {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
    }, []);

    const toggleLogs = (missionId: string) => {
        setExpandedLogs(prev => {
            const next = new Set(prev);
            if (next.has(missionId)) next.delete(missionId);
            else next.add(missionId);
            return next;
        });
    };

    // Map backend phase names to frontend phase names
    const mapPhase = (backendPhase: string): string => {
        switch (backendPhase) {
            case 'brainstorming': return 'brainstorming';
            case 'executing': return 'executing';
            case 'deep_dive': return 'analyzing';
            case 'correlating': return 'correlating';
            case 'briefing': return 'briefing';
            case 'complete': return 'complete';
            case 'error': return 'error';
            default: return 'executing';
        }
    };

    const runScan = useCallback(() => {
        // Reset state
        setDetections([]);
        setClusters([]);
        setNarrative(null);
        setMissionPlan([]);
        setPhase('brainstorming');
        setProgress({ completed: 0, total: 0 });
        stopPolling();

        // POST to start the scan, then poll for status
        fetch(`${API_BASE_URL}/api/v1/sentinel/scan/start`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                const scanId: string = data.scan_id;

                const poll = async () => {
                    try {
                        const res = await fetch(`${API_BASE_URL}/api/v1/sentinel/scan/status/${scanId}`);
                        if (!res.ok) return; // transient error, keep polling
                        const status = await res.json();

                        // Update all UI state from the poll response
                        setPhase(mapPhase(status.phase));
                        if (status.progress) setProgress(status.progress);
                        if (status.missions?.length) setMissionPlan(status.missions);
                        if (status.detections) setDetections(status.detections);
                        if (status.clusters) setClusters(status.clusters);
                        if (status.narrative) setNarrative(status.narrative);
                        if (status.adaptive_context) setAdaptiveContext(status.adaptive_context);

                        // Stop polling when scan is done
                        if (status.status === 'complete') {
                            stopPolling();
                            setScanCount(prev => prev + 1);
                            setPhase('complete');
                        } else if (status.status === 'failed') {
                            stopPolling();
                            setPhase('error');
                        }
                    } catch {
                        // Network error — keep polling, don't crash
                        console.warn('Poll failed, retrying...');
                    }
                };

                // Start polling
                pollRef.current = setInterval(poll, POLL_INTERVAL);
                // Also do one immediate poll
                poll();
            })
            .catch(() => {
                setPhase('error');
            });
    }, [stopPolling]);

    // Cleanup polling on unmount
    useEffect(() => {
        return () => stopPolling();
    }, [stopPolling]);

    // Load historical scan data when prop changes
    useEffect(() => {
        if (historicalScan) {
            stopPolling();
            setDetections(historicalScan.detections || []);
            setClusters(historicalScan.clusters || []);
            setNarrative(historicalScan.narrative || null);
            setMissionPlan([]);
            setPhase('complete');
            setProgress({
                completed: historicalScan.detections?.length || 0,
                total: historicalScan.detections?.length || 0,
            });
        }
    }, [historicalScan]);

    const isHistorical = !!historicalScan;

    // ─── Derived data ───────────────────────────────────────────────────

    const primaryDetections = detections.filter(d => !d.depth || d.depth === 0);
    const subFindings = detections.filter(d => d.depth && d.depth > 0);
    const criticalCount = detections.filter(d => d.severity === 'CRITICAL').length;

    const grouped = {
        security: primaryDetections.filter(d => d.domain === 'security' || d.domain === 'risk'),
        compliance: primaryDetections.filter(d => d.domain === 'compliance'),
        operations: primaryDetections.filter(d => d.domain === 'operations'),
    };

    const getSubFindings = (parentId: string) =>
        subFindings.filter(d => d.parent_mission_id === parentId);

    // ─── Render helpers ─────────────────────────────────────────────────

    const renderRiskGauge = (score: number) => {
        const color = score >= 75 ? '#ef4444' : score >= 50 ? '#f59e0b' : score >= 25 ? '#6366f1' : '#10b981';
        const dashLen = score * 1.57;
        return (
            <div className="risk-gauge" title={`Risk Score: ${score}/100`}>
                <svg viewBox="0 0 120 65" className="gauge-svg">
                    <path d="M10 58 A50 50 0 0 1 110 58" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="8" strokeLinecap="round" />
                    <path d="M10 58 A50 50 0 0 1 110 58" fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
                        strokeDasharray={`${dashLen} 157`} className="gauge-fill" />
                </svg>
                <span className="gauge-score" style={{ color }}>{score}</span>
            </div>
        );
    };

    const renderMiniChart = (det: Detection) => {
        if (!det.results?.length || !det.visualization_config || det.visualization_config.chart_type === 'table') return null;
        const config = det.visualization_config;
        const rows = det.results.slice(0, 5);
        const xKey = config.x_axis_key;
        const yKey = Array.isArray(config.y_axis_key) ? config.y_axis_key[0] : config.y_axis_key;
        const chartData = {
            labels: rows.map(r => r[xKey] || 'N/A'),
            datasets: [{ label: yKey, data: rows.map(r => parseFloat(r[yKey]) || 0), backgroundColor: 'rgba(99,102,241,0.4)', borderColor: '#6366f1', borderWidth: 1 }],
        };
        const opts: any = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } };
        return (
            <div className="mini-chart">
                {config.chart_type === 'line' ? <Line data={chartData} options={opts} /> : <Bar data={chartData} options={opts} />}
            </div>
        );
    };

    const renderDetectionCard = (det: Detection) => {
        const subs = getSubFindings(det.mission_id);
        const isInvestigating = phase !== 'complete' && det.risk_score >= 40;
        return (
            <div key={det.mission_id} className={`detection-card severity-${det.severity}`} data-mission-id={det.mission_id}>
                <div className="detection-meta">
                    <div className="meta-left">
                        <span className={`severity-pill ${det.severity}`}>{det.severity}</span>
                        {det.risk_score > 0 && renderRiskGauge(det.risk_score)}
                    </div>
                    <span className="detection-time">
                        {isInvestigating ? <span className="investigating-badge">INVESTIGATING...</span> : 'LIVE'}
                    </span>
                </div>

                <div className="detection-body">
                    <h5>{det.mission_name}</h5>
                    {renderMiniChart(det)}
                    <div className="compact-insight">
                        <ReactMarkdown>{det.insight || 'Analyzing...'}</ReactMarkdown>
                    </div>
                    {det.recommendation && (
                        <div className="mini-rec">
                            <strong>Protocol:</strong>{' '}
                            {Array.isArray(det.recommendation) ? det.recommendation[0] : String(det.recommendation).substring(0, 120)}
                        </div>
                    )}
                </div>

                {/* Agent Logs */}
                {det.logs && det.logs.length > 0 && (
                    <div className="agent-logs-section">
                        <button className="logs-toggle" onClick={() => toggleLogs(det.mission_id)}>
                            <span className="logs-toggle-icon">{expandedLogs.has(det.mission_id) ? '▾' : '▸'}</span>
                            <span>Agent Logs</span>
                            <span className="logs-count">{det.logs.length}</span>
                        </button>
                        {expandedLogs.has(det.mission_id) && (
                            <div className="logs-panel">
                                {det.logs.map((log, i) => (
                                    <div key={i} className={`log-entry log-${log.level}`}>
                                        <span className="log-node">{log.node}</span>
                                        <span className="log-level">{log.level}</span>
                                        <span className="log-msg">{log.msg}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* Deep Dive Sub-Findings */}
                {subs.length > 0 && (
                    <div className="sub-findings">
                        <div className="sub-findings-header">Deep Dive Findings</div>
                        {subs.map(sub => (
                            <div key={sub.mission_id} className={`sub-finding-card severity-${sub.severity}`}>
                                <div className="sub-finding-connector" />
                                <div className="sub-meta">
                                    <span className={`severity-pill small ${sub.severity}`}>{sub.severity}</span>
                                    {sub.risk_score > 0 && <span className="sub-risk-score">{sub.risk_score}</span>}
                                </div>
                                <h6>{sub.mission_name}</h6>
                                {sub.rationale && <div className="sub-rationale">{sub.rationale}</div>}
                                <div className="compact-insight">
                                    <ReactMarkdown>{sub.insight || 'Analyzing...'}</ReactMarkdown>
                                </div>
                                {sub.data_count > 0 && <span className="data-badge">{sub.data_count} records</span>}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        );
    };

    // ─── Skeleton cards while loading ───────────────────────────────────

    const renderSkeletons = () => {
        const pending = missionPlan.filter(m => !detections.find(d => d.mission_id === m.id));
        if (!pending.length) return null;
        return pending.map(m => (
            <div key={`skel-${m.id}`} className="detection-card skeleton">
                <div className="skeleton-line w60" />
                <div className="skeleton-line w80" />
                <div className="skeleton-line w40" />
            </div>
        ));
    };

    // ─── Main Render ────────────────────────────────────────────────────

    return (
        <div className="sentinel-dashboard">
            {/* Historical Scan Banner */}
            {isHistorical && (
                <div className="history-banner">
                    <div className="history-banner-info">
                        <span className="history-banner-badge">ARCHIVED SCAN</span>
                        <span>Viewing scan from {new Date(historicalScan!.timestamp + 'Z').toLocaleString()}</span>
                    </div>
                    <button className="back-to-live-btn" onClick={onBackToLive}>
                        Back to Live
                    </button>
                </div>
            )}

            {/* Header */}
            <div className="sentinel-header">
                <div className="sentinel-title-group">
                    <span className="sentinel-badge">{isHistorical ? 'SCAN ARCHIVE' : 'LIVE MONITORING'}</span>
                    <h2>Sentinel Mission Control</h2>
                    {!isHistorical && adaptiveContext?.scan_count > 0 && (
                        <span className="adaptive-badge">ADAPTIVE MODE — Scan #{adaptiveContext.scan_count + 1}</span>
                    )}
                </div>
                <div className="sentinel-actions">
                    {!isHistorical && (
                        <button onClick={runScan} className="refresh-btn" disabled={phase !== 'complete' && phase !== 'idle' && phase !== 'error'}>
                            {phase === 'complete' || phase === 'idle' || phase === 'error' ? 'New Scan' : 'Scanning...'}
                        </button>
                    )}
                </div>
            </div>

            {/* Stats */}
            <div className="sentinel-stats-grid">
                <div className="sentinel-stat-card">
                    <div className="stat-label">System Scans</div>
                    <div className="stat-value">{scanCount}</div>
                </div>
                <div className="sentinel-stat-card">
                    <div className="stat-label">Critical Alerts</div>
                    <div className="stat-value warning">{criticalCount}</div>
                </div>
                <div className="sentinel-stat-card">
                    <div className="stat-label">AI Detections</div>
                    <div className="stat-value success">{detections.length}</div>
                </div>
                <div className="sentinel-stat-card">
                    <div className="stat-label">Scan Progress</div>
                    <div className="stat-value">{progress.completed}/{progress.total}</div>
                    {progress.total > 0 && (
                        <div className="progress-bar">
                            <div className="progress-fill" style={{ width: `${(progress.completed / progress.total) * 100}%` }} />
                        </div>
                    )}
                </div>
            </div>

            {/* Phase Indicator */}
            {phase !== 'idle' && phase !== 'complete' && (
                <div className="phase-indicator">
                    <div className="scanner-bar" />
                    <p>
                        {phase === 'brainstorming' && 'Sentinel Brain generating audit missions...'}
                        {phase === 'executing' && `Executing missions (${progress.completed}/${progress.total})...`}
                        {phase === 'analyzing' && 'Deep-dive investigation in progress...'}
                        {phase === 'correlating' && 'Cross-domain threat correlation...'}
                        {phase === 'briefing' && 'Generating executive intelligence brief...'}
                        {phase === 'error' && 'Scan error — click New Scan to retry.'}
                    </p>
                </div>
            )}

            {/* Intelligence Brief */}
            {narrative && (
                <div className={`intelligence-brief severity-${narrative.overall_severity}`}>
                    <div className="brief-header">
                        <div className="brief-badge">INTELLIGENCE BRIEF</div>
                        {renderRiskGauge(narrative.overall_risk)}
                    </div>
                    <div className="brief-summary">
                        <ReactMarkdown>{narrative.executive_summary}</ReactMarkdown>
                    </div>
                    {narrative.threat_vectors.length > 0 && (
                        <div className="threat-vectors">
                            <h4>Threat Vectors</h4>
                            {narrative.threat_vectors.map((tv, i) => (
                                <div key={i} className={`threat-vector-item severity-${tv.severity}`}>
                                    <span className={`severity-pill small ${tv.severity}`}>{tv.severity}</span>
                                    <strong>{tv.name}</strong>
                                    <p>{tv.description}</p>
                                </div>
                            ))}
                        </div>
                    )}
                    <div className="actions-grid">
                        <div className="immediate-actions">
                            <h4>Immediate Actions</h4>
                            <ol>{narrative.immediate_actions.map((a, i) => <li key={i}>{a}</li>)}</ol>
                        </div>
                        <div className="monitoring-recs">
                            <h4>Monitoring Recommendations</h4>
                            <ul>{narrative.monitoring_recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
                        </div>
                    </div>
                </div>
            )}

            {/* Threat Clusters */}
            {clusters.length > 0 && (
                <div className="threat-clusters-section">
                    <div className="clusters-header">
                        <span className="clusters-badge">CROSS-DOMAIN CORRELATIONS</span>
                        <h3>Threat Clusters</h3>
                    </div>
                    <div className="clusters-grid">
                        {clusters.map(cluster => (
                            <div key={cluster.cluster_id} className={`cluster-card severity-${cluster.severity}`}>
                                <div className="cluster-top">
                                    <span className={`severity-pill ${cluster.severity}`}>{cluster.severity}</span>
                                    <h5>{cluster.threat_name}</h5>
                                </div>
                                <div className="cluster-narrative">
                                    <ReactMarkdown>{cluster.narrative}</ReactMarkdown>
                                </div>
                                <div className="cluster-entities">
                                    {cluster.shared_entities.user_ids?.length ? (
                                        <span className="entity-tag">Users: {cluster.shared_entities.user_ids.join(', ')}</span>
                                    ) : null}
                                    {cluster.shared_entities.countries?.length ? (
                                        <span className="entity-tag">Countries: {cluster.shared_entities.countries.join(', ')}</span>
                                    ) : null}
                                    {cluster.shared_entities.ip_addresses?.length ? (
                                        <span className="entity-tag">IPs: {cluster.shared_entities.ip_addresses.join(', ')}</span>
                                    ) : null}
                                </div>
                                <div className="cluster-action">
                                    <strong>Action:</strong> {cluster.recommended_action}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* 3-Column Detection Grid */}
            <div className="sentinel-grid-3">
                {(['security', 'compliance', 'operations'] as const).map(col => (
                    <div key={col} className="sentinel-section">
                        <div className="section-header">
                            <span className="icon">{col === 'security' ? '🛡️' : col === 'compliance' ? '📜' : '📈'}</span>
                            <h4>{col === 'security' ? 'Security & Risk' : col === 'compliance' ? 'Compliance' : 'Operations'}</h4>
                            <span className="section-count">{grouped[col].length}</span>
                        </div>
                        <div className="mission-list">
                            {grouped[col].map(renderDetectionCard)}
                            {phase === 'executing' && renderSkeletons()}
                            {phase === 'complete' && grouped[col].length === 0 && (
                                <div className="empty-section">No findings</div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
