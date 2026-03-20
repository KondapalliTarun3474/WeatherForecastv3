import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Wind, Thermometer, Sun, Droplets, Eye, Gauge, CloudRain, Map as MapIcon, Calendar, LogOut
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs) {
    return twMerge(clsx(inputs));
}

const WeatherTile = ({ title, value, unit, icon: Icon, description, className }) => (
    <div className={cn("relative overflow-hidden rounded-xl bg-white/5 p-6 backdrop-blur-md border border-white/10 hover:bg-white/10 transition-all", className)}>
        <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-slate-400">{title}</h3>
            {Icon && <Icon className="h-5 w-5 text-blue-400" />}
        </div>
        <div className="mt-4">
            <div className="flex items-baseline">
                <span className="text-3xl font-bold text-white">{value}</span>
                <span className="ml-1 text-sm text-slate-400">{unit}</span>
            </div>
            {description && <p className="mt-2 text-xs text-slate-500">{description}</p>}
        </div>
    </div>
);

const HistoryGraph = ({ data, dataKey, color = "#3b82f6" }) => {
    return (
        <div className="h-[300px] w-full mt-4">
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis
                        dataKey="date"
                        stroke="#94a3b8"
                        fontSize={12}
                        tickFormatter={(str) => new Date(str).toLocaleDateString(undefined, { weekday: 'short' })}
                    />
                    <YAxis stroke="#94a3b8" fontSize={12} />
                    <Tooltip
                        contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', color: '#fff' }}
                    />
                    <Line
                        type="monotone"
                        dataKey={dataKey}
                        stroke={color}
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 6 }}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
};


const Dashboard = () => {
    const navigate = useNavigate();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [location, setLocation] = useState({ lat: null, lon: null });
    const [userRole, setUserRole] = useState('');
    const [requestStatus, setRequestStatus] = useState('none'); // none, pending, approved
    const [usersList, setUsersList] = useState([]);
    const [adminRequests, setAdminRequests] = useState([]); // New state for notifications
    const [graphMetric, setGraphMetric] = useState('t2m');
    const [history, setHistory] = useState([]);

    useEffect(() => {
        // Check Auth
        const role = localStorage.getItem('role');
        const username = localStorage.getItem('username');
        setUserRole(role);

        if (role !== 'admin' && role !== 'user' && role !== 'debugger') {
            navigate('/');
            return;
        }

        // Debugger Logic
        if (role === 'debugger') {
            fetch('http://localhost:5000/audit/logs')
                .then(res => res.json())
                .then(data => setData({ logs: data.logs })) // Reuse 'data' state for logs
                .catch(err => console.error(err));
            setLoading(false);
            return; // Debugger doesn't need weather data
        }

        // Check Access Request Status (for non-admin)
        if (role === 'user') {
            // New endpoint returns 'none', 'pending', or 'approved'
            fetch(`http://localhost:5000/access/status?username=${username}`)
                .then(res => res.json())
                .then(data => setRequestStatus(data.status))
                .catch(err => console.error("Status check failed", err));
        }

        // Load Users AND Pending Requests (for admin)
        if (role === 'admin') {
            const fetchUsers = fetch('http://localhost:5000/users').then(res => res.json());
            const fetchPending = fetch('http://localhost:5000/users/pending').then(res => res.json());

            Promise.all([fetchUsers, fetchPending])
                .then(([usersData, pendingData]) => {
                    setUsersList(usersData.users);
                    setAdminRequests(pendingData.users);
                })
                .catch(err => console.error("Admin data fetch failed", err));
        }

        // Get Location
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    setLocation({
                        lat: position.coords.latitude,
                        lon: position.coords.longitude
                    });
                },
                (err) => {
                    setError('Location access denied. Using London as default.');
                    setLocation({ lat: 51.5074, lon: -0.1278 }); // London fallback
                }
            );
        } else {
            setError('Geolocation not supported. Using London as default.');
            setLocation({ lat: 51.5074, lon: -0.1278 });
        }
    }, [navigate]);

    // Fetch History if approved
    useEffect(() => {
        const username = localStorage.getItem('username');
        if (requestStatus === 'approved' && username) {
            // Note: In local dev this might fail if not proxied correctly, 
            // but in K8s it goes through /api/db/
            fetch(`http://localhost:5000/access/status?username=${username}`) // Dummy to ensure we have latest status

            // Real history fetch - using auth port 5000 as proxy or direct db-service if local
            // Better to use the relative path /api/db/ for production-ready frontend
            const historyUrl = window.location.hostname === 'localhost'
                ? `http://localhost:5001/history?username=${username}` // Proxy via inference service
                : `/api/db/inference-log/${username}`;

            fetch(historyUrl)
                .then(res => res.json())
                .then(data => setHistory(data.history || []))
                .catch(err => console.error("History fetch failed", err));
        }
    }, [requestStatus]);

    const handleToggleAccess = async (user, currentAccess) => {
        try {
            await fetch('http://localhost:5000/users/toggle-access', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, access: !currentAccess })
            });

            // Update users list
            setUsersList(prev => prev.map(u =>
                u.username === user ? { ...u, has_llm_access: !currentAccess } : u
            ));

            // If access granted, remove from notification bar
            if (!currentAccess) {
                setAdminRequests(prev => prev.filter(u => u !== user));
            }

        } catch (err) {
            console.error("Toggle failed", err);
        }
    };

    const handleDeleteUser = async (user) => {
        if (!window.confirm(`Are you sure you want to delete ${user}?`)) return;
        try {
            await fetch('http://localhost:5000/users/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user })
            });
            // Update states
            setUsersList(prev => prev.filter(u => u.username !== user));
            setAdminRequests(prev => prev.filter(u => u !== user));
        } catch (err) {
            console.error("Delete failed", err);
        }
    };

    const handleRequestAccess = async () => {
        const username = localStorage.getItem('username');
        try {
            await fetch('http://localhost:5000/access/request', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            setRequestStatus('pending');
        } catch (err) {
            console.error("Request failed", err);
        }
    };

    const handleRedeemService = async () => {
        if (!window.confirm("Are you sure you want to remove your LLM Prediction service?")) return;
        const username = localStorage.getItem('username');
        try {
            await fetch('http://localhost:5000/access/revoke', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            setRequestStatus('none');
        } catch (err) {
            console.error("Redeem failed", err);
        }
    };

    const handleSelfDelete = async () => {
        if (!window.confirm("Are you sure you want to PERMANENTLY delete your account? This cannot be undone.")) return;
        const username = localStorage.getItem('username');
        try {
            await fetch('http://localhost:5000/users/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            });
            // Logout logic
            localStorage.clear();
            navigate('/');
        } catch (err) {
            console.error("Self delete failed", err);
        }
    };

    useEffect(() => {
        if (!location.lat || !location.lon) return;

        const fetchData = async () => {
            try {
                setLoading(true);
                // Fetch Current & Daily (Past 10 days)
                const weatherUrl = `https://api.open-meteo.com/v1/forecast?latitude=${location.lat}&longitude=${location.lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,surface_pressure,wind_speed_10m,wind_direction_10m,visibility&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max,precipitation_sum&past_days=10&forecast_days=1`;

                const aqUrl = `https://air-quality-api.open-meteo.com/v1/air-quality?latitude=${location.lat}&longitude=${location.lon}&current=us_aqi`;

                const [weatherRes, aqRes] = await Promise.all([
                    fetch(weatherUrl),
                    fetch(aqUrl)
                ]);

                const weatherData = await weatherRes.json();
                const aqData = await aqRes.json();

                setData({ weather: weatherData, aq: aqData });
            } catch (err) {
                console.error(err);
                setError('Failed to fetch weather data.');
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [location]);

    if (loading) return (
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-white">
            <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
        </div>
    );

    // DEBUGGER VIEW
    if (userRole === 'debugger') {
        return (
            <div className="min-h-screen bg-slate-950 p-6 md:p-8 space-y-8">
                <div className="flex justify-between items-center">
                    <h1 className="text-3xl font-light text-white">Audit Logs</h1>
                    <button
                        onClick={() => {
                            localStorage.clear();
                            navigate('/');
                        }}
                        className="px-4 py-2 bg-slate-800 text-slate-300 rounded hover:bg-slate-700"
                    >
                        Logout
                    </button>
                </div>

                <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
                    <table className="w-full text-left text-sm text-slate-400">
                        <thead className="bg-slate-950 text-slate-200 uppercase font-medium">
                            <tr>
                                <th className="px-6 py-4">Timestamp</th>
                                <th className="px-6 py-4">User</th>
                                <th className="px-6 py-4">Action</th>
                                <th className="px-6 py-4">Details</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                            {data && data.logs ? data.logs.slice().reverse().map((log, i) => (
                                <tr key={i} className="hover:bg-slate-800/50 transition-colors">
                                    <td className="px-6 py-4 font-mono text-xs">{new Date(log.timestamp).toLocaleString()}</td>
                                    <td className="px-6 py-4 text-white">{log.username}</td>
                                    <td className="px-6 py-4 text-blue-400 font-medium">{log.action}</td>
                                    <td className="px-6 py-4 font-mono text-xs text-slate-500">
                                        {JSON.stringify(log.details)}
                                    </td>
                                </tr>
                            )) : (
                                <tr>
                                    <td colSpan="4" className="px-6 py-8 text-center text-slate-600">No logs found.</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    }

    if (!data) return <div className="text-white">Error loading data.</div>;

    const current = data.weather.current;
    const currentUnit = data.weather.current_units;
    const daily = data.weather.daily;
    const aqi = data.aq.current.us_aqi;

    // Process history data for graph
    const historyData = daily.time.map((date, i) => ({
        date,
        t2m: (daily.temperature_2m_max[i] + daily.temperature_2m_min[i]) / 2, // Avg temp
        humidity: 50 + Math.random() * 30
    })).slice(0, 10); // Take first 10 days (past)

    return (
        <div className="min-h-screen bg-slate-950 p-6 md:p-8 space-y-8">
            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h1 className="text-4xl font-light text-white tracking-tight">
                        {location.lat?.toFixed(2)}°, {location.lon?.toFixed(2)}°
                    </h1>
                    <p className="text-slate-400 mt-1 flex items-center gap-2">
                        <MapIcon className="h-4 w-4" /> My Location
                    </p>
                </div>
                <div className="flex flex-col items-end gap-4">
                    {/* Admin Notification Bar */}
                    {userRole === 'admin' && adminRequests.length > 0 && (
                        <div className="animate-in fade-in slide-in-from-top-4 duration-500 w-full md:w-auto">
                            <div className="bg-yellow-500/10 border border-yellow-500/20 px-4 py-2 rounded-lg flex items-center gap-3 shadow-lg shadow-yellow-500/5">
                                <div className="flex h-2 w-2 rounded-full bg-yellow-400 animate-pulse" />
                                <span className="text-yellow-200 text-sm font-medium">Pending Requests:</span>

                                {adminRequests.map(user => (
                                    <div key={user} className="flex items-center gap-2 pl-2 border-l border-yellow-500/20">
                                        <span className="text-white text-sm font-mono">{user}</span>
                                        <button
                                            onClick={() => handleToggleAccess(user, false)} // False -> True
                                            className="text-xs bg-yellow-500 text-black font-bold px-2 py-1 rounded hover:bg-yellow-400 transition-colors"
                                        >
                                            Approve
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="flex items-center gap-4">
                        {/* Admin Panel: Full User Management */}
                        {userRole === 'admin' && (
                            <div className="flex flex-col gap-2 bg-slate-900/50 border border-slate-700/50 px-4 py-3 rounded-lg max-h-60 overflow-y-auto w-full md:w-auto">
                                <h3 className="text-slate-300 text-sm font-medium mb-1">User Management</h3>
                                {usersList.filter(u => u.role !== 'admin').length === 0 && (
                                    <p className="text-slate-500 text-xs">No users found.</p>
                                )}
                                {usersList.filter(u => u.role !== 'admin').map(user => (
                                    <div key={user.username} className="flex items-center justify-between gap-4 bg-white/5 p-2 rounded">
                                        <span className="text-white text-sm font-mono">{user.username}</span>
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={() => handleToggleAccess(user.username, user.has_llm_access)}
                                                className={`text-xs px-2 py-1 rounded transition-colors ${user.has_llm_access
                                                    ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                                                    : 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                                                    }`}
                                            >
                                                {user.has_llm_access ? 'Access ON' : 'Access OFF'}
                                            </button>
                                            <button
                                                onClick={() => handleDeleteUser(user.username)}
                                                className="text-xs bg-slate-700 text-slate-300 px-2 py-1 rounded hover:bg-red-600 hover:text-white transition-colors"
                                                title="Delete User"
                                            >
                                                X
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* User Actions */}
                        {userRole === 'user' && (
                            <div className="flex items-center gap-2">
                                {/* Redeem Service (Revoke Access) */}
                                {requestStatus === 'approved' && (
                                    <button
                                        onClick={handleRedeemService}
                                        className="px-3 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-300 border border-red-500/20 rounded-lg text-sm transition-colors"
                                        title="Remove LLM Service"
                                    >
                                        Remove Service
                                    </button>
                                )}

                                {/* LLM Prediction / Request Access */}
                                {requestStatus === 'approved' ? (
                                    <button
                                        onClick={() => navigate('/llm-forecast')}
                                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors shadow-lg shadow-indigo-500/20"
                                    >
                                        LLM Prediction
                                    </button>
                                ) : (
                                    <button
                                        onClick={handleRequestAccess}
                                        disabled={requestStatus === 'pending'}
                                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${requestStatus === 'pending'
                                            ? 'bg-yellow-500/10 text-yellow-200 border border-yellow-500/20 cursor-not-allowed'
                                            : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 hover:border-slate-600'
                                            }`}
                                    >
                                        {requestStatus === 'pending' ? 'Request Pending...' : 'Request Prediction Access'}
                                    </button>
                                )}

                                {/* Delete Account */}
                                <button
                                    onClick={handleSelfDelete}
                                    className="px-3 py-2 bg-slate-800 hover:bg-red-900/50 text-slate-400 hover:text-red-200 border border-slate-700 rounded-lg text-sm transition-colors"
                                    title="Delete Account"
                                >
                                    Delete Account
                                </button>
                            </div>
                        )}

                        {/* Admin LLM Link (Separate to avoid complex nesting above) */}
                        {userRole === 'admin' && (
                            <button
                                onClick={() => navigate('/llm-forecast')}
                                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors shadow-lg shadow-indigo-500/20"
                            >
                                LLM Prediction
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Large Main Card (Temperature) */}
                <div className="col-span-1 md:col-span-2 row-span-2 rounded-2xl bg-gradient-to-br from-blue-600/20 to-indigo-600/20 p-8 border border-white/10 backdrop-blur-xl flex flex-col justify-between">
                    <div>
                        <h2 className="text-lg text-blue-200">Now</h2>
                        <div className="flex items-baseline mt-2">
                            <span className="text-7xl font-thin text-white">{current.temperature_2m}</span>
                            <span className="text-2xl text-blue-200 font-light">{currentUnit.temperature_2m}</span>
                        </div>
                        <p className="text-blue-200 mt-2 text-lg">
                            {/* Weather Code Mapping could go here */}
                            Most Likely Clear
                        </p>
                    </div>
                    <div className="flex gap-8 text-sm text-slate-300">
                        <div>
                            <p className="text-slate-500">H: {daily.temperature_2m_max[0]}°</p>
                            <p className="text-slate-500">L: {daily.temperature_2m_min[0]}°</p>
                        </div>
                        <div>
                            <p>Wind Gusts: {current.wind_speed_10m} {currentUnit.wind_speed_10m}</p>
                        </div>
                    </div>
                </div>

                {/* Small Tiles */}
                <WeatherTile
                    title="Air Quality"
                    value={aqi}
                    unit="AQI"
                    icon={CloudRain}
                    description={aqi < 50 ? "Good" : "Moderate"}
                    className={aqi > 100 ? "bg-red-500/10 border-red-500/20" : "bg-green-500/10 border-green-500/20"}
                />
                <WeatherTile
                    title="UV Index"
                    value={daily.uv_index_max[0]}
                    unit=""
                    icon={Sun}
                    description="Max today"
                />
                <WeatherTile
                    title="Wind"
                    value={current.wind_speed_10m}
                    unit="km/h"
                    icon={Wind}
                    description={`Dir: ${current.wind_direction_10m}°`}
                />
                <WeatherTile
                    title="Humidity"
                    value={current.relative_humidity_2m}
                    unit="%"
                    icon={Droplets}
                    description={`Dew Point: ${(current.temperature_2m - (100 - current.relative_humidity_2m) / 5).toFixed(1)}°`}
                />
                <WeatherTile
                    title="Visibility"
                    value={current.visibility / 1000}
                    unit="km"
                    icon={Eye}
                />
                <WeatherTile
                    title="Pressure"
                    value={current.surface_pressure}
                    unit="hPa"
                    icon={Gauge}
                />
            </div>

            {/* Graph Section */}
            <div className="rounded-2xl bg-white/5 p-6 border border-white/10 backdrop-blur-md">
                <div className="flex items-center justify-between mb-6">
                    <h3 className="text-lg font-medium text-white flex items-center gap-2">
                        <Calendar className="h-5 w-5 text-blue-400" />
                        History & Trend
                    </h3>
                    <select
                        value={graphMetric}
                        onChange={(e) => setGraphMetric(e.target.value)}
                        className="bg-black/40 border border-white/20 rounded-lg px-3 py-1 text-sm text-white focus:outline-none focus:border-blue-500"
                    >
                        <option value="t2m">Temperature ({currentUnit.temperature_2m})</option>
                        <option value="humidity">Humidity (%)</option>
                    </select>
                </div>

                <HistoryGraph
                    data={historyData}
                    dataKey={graphMetric}
                    color={graphMetric === 't2m' ? '#60a5fa' : '#34d399'}
                />
            </div>

            {/* Recent Predictions History (User Specific) */}
            {requestStatus === 'approved' && (
                <div className="rounded-2xl bg-white/5 p-6 border border-white/10 backdrop-blur-md animate-in fade-in slide-in-from-bottom-4 duration-700">
                    <h3 className="text-lg font-medium text-white mb-6 flex items-center gap-2">
                        <Calendar className="h-5 w-5 text-indigo-400" />
                        Recent Predictions
                    </h3>
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm text-slate-400">
                            <thead className="text-slate-500 uppercase text-xs font-semibold border-b border-white/5">
                                <tr>
                                    <th className="px-4 py-3">Model</th>
                                    <th className="px-4 py-3">Coordinates</th>
                                    <th className="px-4 py-3">Time</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                                {history.length > 0 ? history.map((log, i) => (
                                    <tr key={i} className="hover:bg-white/5 transition-colors">
                                        <td className="px-4 py-4">
                                            <span className="px-2 py-1 bg-indigo-500/10 text-indigo-400 rounded text-xs font-mono">
                                                {log.model_name}
                                            </span>
                                        </td>
                                        <td className="px-4 py-4 text-slate-300 font-mono">
                                            {log.lat?.toFixed(2)}, {log.lon?.toFixed(2)}
                                        </td>
                                        <td className="px-4 py-4 text-xs text-slate-500">
                                            {new Date(log.timestamp).toLocaleString()}
                                        </td>
                                    </tr>
                                )) : (
                                    <tr>
                                        <td colSpan="3" className="px-4 py-8 text-center text-slate-600 italic">
                                            No recent predictions found.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
            {/* Floating Logout Button */}
            <button
                onClick={() => {
                    localStorage.clear();
                    navigate('/');
                }}
                className="fixed bottom-6 left-6 px-4 py-2 bg-slate-800/80 hover:bg-red-900/50 text-slate-300 hover:text-red-200 border border-slate-700 backdrop-blur-md rounded-lg shadow-2xl z-50 transition-all flex items-center gap-2 group"
            >
                <LogOut className="h-4 w-4 group-hover:text-red-400 transition-colors" />
                <span className="font-medium">Logout</span>
            </button>
        </div>
    );
};

export default Dashboard;
