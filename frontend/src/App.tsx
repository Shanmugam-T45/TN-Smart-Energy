import { useState } from 'react'
import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  Bell,
  Bolt,
  Building2,
  ChevronDown,
  CircleGauge,
  FileText,
  Gauge,
  Home,
  LayoutDashboard,
  Menu,
  MapPin,
  ShieldCheck,
  SlidersHorizontal,
  UploadCloud,
  Zap,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { DatasetProvider } from './DatasetContext'
import { useDatasets } from './useDatasets'
import DatasetUpload from './DatasetUpload'
import { PUBLIC_DEMO_MODE } from './datasetApi'
import HouseholdMonitoringPage from './HouseholdMonitoringPage'
import TransformerMonitoringPage from './TransformerMonitoringPage'
import ForecastPage from './ForecastPage'
import ConservationPage from './ConservationPage'
import VoltagePage from './VoltagePage'
import OutagesPage from './OutagesPage'
import LossAnalysisPage from './LossAnalysisPage'
import ReportsPage from './ReportsPage'
import './App.css'

const demandData = [
  { time: '00:00', demand: 42, predicted: 43 },
  { time: '03:00', demand: 38, predicted: 39 },
  { time: '06:00', demand: 51, predicted: 49 },
  { time: '09:00', demand: 68, predicted: 66 },
  { time: '12:00', demand: 74, predicted: 72 },
  { time: '15:00', demand: 70, predicted: 73 },
  { time: '18:00', demand: 86, predicted: 84 },
  { time: '21:00', demand: 79, predicted: 81 },
]

const consumptionData = [
  { name: 'Mon', value: 812 },
  { name: 'Tue', value: 894 },
  { name: 'Wed', value: 856 },
  { name: 'Thu', value: 948 },
  { name: 'Fri', value: 921 },
  { name: 'Sat', value: 768 },
  { name: 'Sun', value: 735 },
]

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/meters', label: 'Household meters', icon: Home },
  { to: '/forecast', label: 'Forecasting', icon: Activity },
  { to: '/transformers', label: 'Transformers', icon: Bolt },
  { to: '/conservation', label: 'Conservation', icon: SlidersHorizontal },
  { to: '/voltage', label: 'Voltage Analysis', icon: Gauge },
  { to: '/outages', label: 'Outages', icon: Zap },
  { to: '/losses', label: 'Loss Analysis', icon: BarChart3 },
  { to: '/simulator', label: 'Simulator', icon: CircleGauge },
  { to: '/map', label: 'Locality Map', icon: MapPin },
  { to: '/reports', label: 'Reports', icon: FileText },
]

function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { datasets, selectedDatasetId, selectDataset, apiError } = useDatasets()

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Zap size={22} fill="currentColor" /></div>
          <div>
            <strong>TN SMART ENERGY</strong>
            <span>Reliability Console</span>
          </div>
        </div>
        <nav>
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} onClick={() => setMenuOpen(false)}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="system-status"><span className="status-dot" /> System operational</div>
          <button className="profile">
            <div className="avatar">SA</div>
            <div><strong>System Analyst</strong><span>Energy Analyst</span></div>
            <ChevronDown size={16} />
          </button>
        </div>
      </aside>
      {menuOpen && <button className="backdrop" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}

      <main>
        <header className="topbar">
          <button className="icon-button menu-button" aria-label="Open menu" onClick={() => setMenuOpen(true)}><Menu size={20} /></button>
          <div className="topbar-title">
            <span>OPERATIONS /</span>
            <strong> TAMIL NADU DEMO GRID</strong>
          </div>
          <div className="topbar-actions">
            {!PUBLIC_DEMO_MODE && (
              <>
                <label className="visually-hidden" htmlFor="active-dataset">Active dataset</label>
                <select
                  id="active-dataset"
                  className="dataset-select"
                  value={selectedDatasetId ?? 'demo'}
                  onChange={(event) => selectDataset(event.target.value === 'demo' ? null : Number(event.target.value))}
                >
                  <option value="demo">Demo data</option>
                  {datasets.map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>{dataset.filename}</option>
                  ))}
                </select>
              </>
            )}
            <span className={`demo-pill ${selectedDatasetId !== null && !PUBLIC_DEMO_MODE ? 'uploaded-pill' : ''}`}>
              {PUBLIC_DEMO_MODE ? 'PUBLIC DEMO' : selectedDatasetId !== null ? 'UPLOADED DATA' : 'SIMULATED DATA'}
            </span>
            <button className="icon-button" aria-label="Notifications"><Bell size={18} /><span className="notification-dot" /></button>
            {!PUBLIC_DEMO_MODE && <DatasetUpload />}
          </div>
        </header>
        {PUBLIC_DEMO_MODE && (
          <div className="public-demo-banner" role="status">
            Read-only public demo: all readings are synthetic. Uploads and saved changes are disabled; no private application database is used.
          </div>
        )}
        {apiError && (
          <div className="api-warning" role="status">
            Dataset service unavailable: {apiError}. {PUBLIC_DEMO_MODE ? 'The public demo dataset is unavailable until the service recovers.' : 'Demo data remains available.'}
          </div>
        )}
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/meters" element={<HouseholdMonitoringPage />} />
          <Route path="/forecast" element={<ForecastPage />} />
          <Route path="/transformers" element={<TransformerMonitoringPage />} />
          <Route path="/conservation" element={<ConservationPage />} />
          <Route path="/voltage" element={<VoltagePage />} />
          <Route path="/outages" element={<OutagesPage />} />
          <Route path="/losses" element={<LossAnalysisPage />} />
          <Route path="/simulator" element={<ConservationPage />} />
          <Route path="/map" element={<SimplePage title="Locality and Asset Map" icon={MapPin} />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

function Dashboard() {
  const { selectedDatasetId, selectedSummary, isLoadingSummary } = useDatasets()
  const uploaded = selectedDatasetId !== null
  const demandChartData = uploaded
    ? (selectedSummary?.demand_series ?? []).map((point) => ({
        time: point.timestamp.slice(11, 16),
        demand: point.demand_kw,
      }))
    : demandData
  const consumptionChartData = uploaded
    ? (selectedSummary?.consumption_series ?? []).map((point) => ({
        name: new Date(`${point.date}T00:00:00Z`).toLocaleDateString('en', { weekday: 'short', timeZone: 'UTC' }),
        value: point.energy_kwh,
      }))
    : consumptionData
  const displayedMetric = (uploadedValue: number | null | undefined, demoValue: string, digits = 1) => {
    if (!uploaded) return demoValue
    if (isLoadingSummary) return '…'
    return uploadedValue === null || uploadedValue === undefined ? '—' : uploadedValue.toLocaleString(undefined, { maximumFractionDigits: digits })
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">SYSTEM OVERVIEW</p>
          <h1>Good morning, Analyst</h1>
        </div>
        <div className="date-control">{PUBLIC_DEMO_MODE ? 'Simulated public dataset' : uploaded ? 'Selected uploaded dataset' : 'Simulated demonstration'} <ChevronDown size={14} /></div>
      </div>

      <div className="notice">
        <ShieldCheck size={17} />
        <span>
          {PUBLIC_DEMO_MODE
            ? <><strong>Public demonstration:</strong> this dataset is generated synthetic data, not live utility readings or customer information.</>
            : uploaded
            ? <><strong>Uploaded data:</strong> {selectedSummary?.filename ?? 'Loading dataset…'} Readings are user-provided and not independently verified.</>
            : <><strong>Demo mode:</strong> All readings and asset locations are simulated. No live TN utility connection is claimed.</>}
        </span>
      </div>

      <section className="metric-grid">
        <Metric
          title="Total energy"
          value={displayedMetric(selectedSummary?.total_energy_kwh, '6,482', 2)}
          unit="kWh"
          change={uploaded ? (PUBLIC_DEMO_MODE ? 'Simulated' : 'Uploaded') : '+6.2%'}
          tone="green"
          icon={Zap}
        />
        <Metric
          title="Current demand"
          value={displayedMetric(selectedSummary?.current_demand_kw, '78.4')}
          unit="kW"
          change={uploaded ? (PUBLIC_DEMO_MODE ? 'Simulated' : selectedSummary?.current_demand_kw == null ? 'No power data' : 'Measured') : '+2.1%'}
          tone="blue"
          icon={Activity}
        />
        <Metric
          title="Peak demand"
          value={displayedMetric(selectedSummary?.maximum_demand_kw, '96.8')}
          unit="kW"
          change={uploaded ? (PUBLIC_DEMO_MODE ? 'Simulated' : selectedSummary?.maximum_demand_kw == null ? 'No power data' : 'Measured') : '+8.4%'}
          tone="amber"
          icon={Gauge}
        />
        <Metric
          title="Peak transformer load"
          value={displayedMetric(selectedSummary?.maximum_transformer_loading_percent, '68.3')}
          unit={uploaded && selectedSummary?.maximum_transformer_loading_percent == null ? '' : '%'}
          change={uploaded
            ? (PUBLIC_DEMO_MODE ? 'Simulated estimate' : selectedSummary?.maximum_transformer_loading_percent == null ? 'Capacity or power factor needed' : 'Uploaded readings estimate')
            : 'Simulated'}
          tone="green"
          icon={Building2}
        />
      </section>

      <section className="dashboard-grid">
        <div className="panel demand-panel">
          <PanelHeader
            title={PUBLIC_DEMO_MODE ? 'Simulated demand' : uploaded ? 'Measured demand' : 'Demand forecast'}
            subtitle={PUBLIC_DEMO_MODE ? 'Synthetic aggregate active power; not model predictions' : uploaded ? 'Aggregated uploaded active power' : 'Demonstration values; not model predictions'}
            badge={PUBLIC_DEMO_MODE ? 'Synthetic demo' : uploaded ? 'Uploaded readings' : 'Simulated'}
          />
          <div className="chart-legend">
            <span><i className="actual" /> {PUBLIC_DEMO_MODE ? 'Simulated demand' : uploaded ? 'Measured' : 'Demo demand'}</span>
            {!uploaded && <span><i className="predicted" /> Demo comparison</span>}
          </div>
          <div className="chart-area">
            {isLoadingSummary ? (
              <div className="chart-empty">Loading selected dataset…</div>
            ) : demandChartData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={demandChartData} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
                  <defs>
                    <linearGradient id="actualFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#1f8a70" stopOpacity={0.22}/>
                      <stop offset="95%" stopColor="#1f8a70" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#edf1ef" />
                  <XAxis dataKey="time" tick={{ fill: '#81908a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#81908a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #e5ebe8', fontSize: 12 }} />
                  <Area type="monotone" dataKey="demand" stroke="#1f8a70" strokeWidth={2.5} fill="url(#actualFill)" />
                  {!uploaded && <Line type="monotone" dataKey="predicted" stroke="#8da39c" strokeWidth={2} strokeDasharray="5 5" dot={false} />}
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="chart-empty">This dataset has no active_power_kw readings to chart.</div>
            )}
          </div>
        </div>

        <div className="panel alerts-panel">
          <PanelHeader title={uploaded ? (PUBLIC_DEMO_MODE ? 'Demo dataset screening' : 'Dataset screening') : 'Active demo alerts'} subtitle={PUBLIC_DEMO_MODE ? 'Simulated voltage readings only' : uploaded ? 'Uploaded voltage readings only' : 'Simulated examples; not verified faults'} badge={uploaded ? String(selectedSummary?.low_voltage_reading_count ?? '…') : '3'} />
          {uploaded ? (
            <div className="uploaded-alert-summary">
              {isLoadingSummary ? 'Loading screening results…' : `${selectedSummary?.low_voltage_reading_count ?? 0} reading(s) below the illustrative ${selectedSummary?.low_voltage_threshold_v ?? 207} V screening threshold.`}
              <small>A voltage screen alone does not confirm an equipment fault.</small>
            </div>
          ) : (
            <>
              <Alert level="high" title="Potential overload" text="T-204 • 84% simulated loading" time="12 min ago" />
              <Alert level="medium" title="Voltage screening" text="Coimbatore East • 211 V reading" time="38 min ago" />
              <Alert level="low" title="Repeated interruptions" text="F-12 • 3 events this month" time="2 hr ago" />
              <button className="text-button">View all alerts</button>
            </>
          )}
        </div>
      </section>

      <section className="dashboard-grid lower">
        <div className="panel">
          <PanelHeader title={uploaded ? 'Recent daily consumption' : 'Weekly consumption'} subtitle={PUBLIC_DEMO_MODE ? 'Synthetic kWh grouped by reading date' : 'kWh • grouped by reading date'} />
          <div className="chart-area small">
            {isLoadingSummary ? (
              <div className="chart-empty">Loading selected dataset…</div>
            ) : consumptionChartData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={consumptionChartData} margin={{ left: -20, right: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#edf1ef" />
                  <XAxis dataKey="name" tick={{ fill: '#81908a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#81908a', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: '#f3f7f5' }} contentStyle={{ borderRadius: 10, border: '1px solid #e5ebe8', fontSize: 12 }} />
                  <Bar dataKey="value" fill="#1f8a70" radius={[5, 5, 0, 0]} barSize={28} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="chart-empty">No consumption readings are available.</div>
            )}
          </div>
        </div>
        <div className="panel">
          <PanelHeader title={uploaded ? 'Dataset summary' : 'Grid health'} subtitle={uploaded ? 'Counts from selected upload' : 'Simulated operating summary'} />
          <div className="health-grid">
            <Health label="Transformers" value={uploaded ? String(selectedSummary?.transformer_count ?? '…') : '24'} detail={uploaded ? 'IDs in this dataset' : '3 require review'} />
            <Health label="Feeders" value={uploaded ? String(selectedSummary?.feeder_count ?? '…') : '48'} detail={uploaded ? 'IDs in this dataset' : 'All reporting'} />
            <Health label="Low voltage" value={uploaded ? String(selectedSummary?.low_voltage_reading_count ?? '…') : '12'} detail={uploaded ? 'Below screening threshold' : 'Simulated readings'} />
            <Health label="Meter readings" value={uploaded ? String(selectedSummary?.record_count ?? '…') : '156'} detail={uploaded ? `${selectedSummary?.meter_count ?? '…'} distinct meters` : 'Simulated uploads'} />
          </div>
        </div>
      </section>
    </div>
  )
}

function Metric({ title, value, unit, change, tone, icon: Icon }: { title: string; value: string; unit: string; change: string; tone: string; icon: typeof Zap }) {
  return (
    <div className="metric-card">
      <div className={`metric-icon ${tone}`}><Icon size={19} /></div>
      <div className="metric-content">
        <span>{title}</span>
        <div><strong>{value}</strong><small>{unit}</small></div>
      </div>
      <span className={`metric-change ${tone}`}>{change}</span>
    </div>
  )
}

function PanelHeader({ title, subtitle, badge }: { title: string; subtitle: string; badge?: string }) {
  return (
    <div className="panel-header">
      <div><h2>{title}</h2><p>{subtitle}</p></div>
      {badge && <span className="panel-badge">{badge}</span>}
    </div>
  )
}

function Alert({ level, title, text, time }: { level: string; title: string; text: string; time: string }) {
  return (
    <button className="alert-row">
      <span className={`alert-level ${level}`} />
      <div><strong>{title}</strong><p>{text}</p></div>
      <time>{time}</time>
    </button>
  )
}

function Health({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="health-item"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
  )
}

function SimplePage({ title, icon: Icon }: { title: string; icon: typeof Zap }) {
  return (
    <div className="page">
      <div className="page-heading"><div><p className="eyebrow">ANALYTICS MODULE</p><h1>{title}</h1></div></div>
      <div className="empty-feature panel">
        <div className="empty-icon"><Icon size={28} /></div>
        <h2>{title} workspace</h2>
        <p>{PUBLIC_DEMO_MODE ? 'This public demo uses synthetic data and is read-only.' : 'Upload an authorised dataset or load the built-in demonstration dataset to begin analysis.'}</p>
        {!PUBLIC_DEMO_MODE && <button className="upload-button"><UploadCloud size={17} /> Upload dataset</button>}
      </div>
    </div>
  )
}


export default function App() {
  return <BrowserRouter><DatasetProvider><AppShell /></DatasetProvider></BrowserRouter>
}
