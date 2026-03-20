import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Search, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import ForecastMap from '../components/ForecastMap';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const LLMForecast = () => {
    const navigate = useNavigate();
    const [lat, setLat] = useState('');
    const [lon, setLon] = useState('');
    const [property, setProperty] = useState('T2M');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');

    const handlePredict = async (e) => {
        e.preventDefault();
        if (!lat || !lon) return;

        setLoading(true);
        setError('');
        setResult(null);

        try {
            // Dynamic Port Selection for Microservices
            let port = 5001;
            if (property === 'RH2M') port = 5002;
            if (property === 'WS2M') port = 5003;

            const username = localStorage.getItem('username') || 'anonymous';

            const response = await fetch(`http://localhost:${port}/forecast`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Username': username
                },
                body: JSON.stringify({
                    lat: parseFloat(lat),
                    lon: parseFloat(lon),
                    property: property
                })
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.error || 'Prediction failed');
            }

            const data = await response.json();
            setResult(data);
        } catch (err) {
            console.error(err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-slate-950 p-6 md:p-8 space-y-8">
            <div className="flex items-center gap-4">
                <button
                    onClick={() => navigate('/dashboard')}
                    className="p-2 hover:bg-white/10 rounded-full text-slate-400 hover:text-white transition-colors"
                >
                    <ArrowLeft className="h-6 w-6" />
                </button>
                <h1 className="text-3xl font-light text-white">LLM4TS Prediction Model</h1>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Control Panel */}
                <div className="lg:col-span-1 space-y-6">
                    <div className="rounded-2xl bg-white/5 p-6 border border-white/10 backdrop-blur-md">
                        <h2 className="text-xl font-medium text-white mb-4">Configuration</h2>
                        <form onSubmit={handlePredict} className="space-y-4">
                            <div>
                                <label className="blocks text-sm font-medium text-slate-400 mb-1">Latitude</label>
                                <input
                                    type="number" step="any"
                                    value={lat} onChange={e => setLat(e.target.value)}
                                    className="w-full bg-black/40 border border-white/20 rounded-lg px-3 py-2 text-white focus:border-blue-500 outline-none"
                                    placeholder="e.g. 12.97"
                                    required
                                />
                            </div>
                            <div>
                                <label className="blocks text-sm font-medium text-slate-400 mb-1">Longitude</label>
                                <input
                                    type="number" step="any"
                                    value={lon} onChange={e => setLon(e.target.value)}
                                    className="w-full bg-black/40 border border-white/20 rounded-lg px-3 py-2 text-white focus:border-blue-500 outline-none"
                                    placeholder="e.g. 77.59"
                                    required
                                />
                            </div>
                            <div>
                                <label className="blocks text-sm font-medium text-slate-400 mb-1">Target Property</label>
                                <select
                                    value={property}
                                    onChange={e => setProperty(e.target.value)}
                                    className="w-full bg-black/40 border border-white/20 rounded-lg px-3 py-2 text-white focus:border-blue-500 outline-none"
                                >
                                    <option value="T2M">Temperature (T2M)</option>
                                    <option value="RH2M">Humidity (RH2M)</option>
                                    <option value="WS2M">Wind Speed (WS2M)</option>
                                </select>
                            </div>

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full mt-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-lg py-2 font-medium transition-all shadow-lg shadow-blue-500/20 disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                                {loading ? 'Running Inference...' : 'Generate Prediction'}
                            </button>
                        </form>
                    </div>

                    {/* Status / Output Text */}
                    {error && (
                        <div className="rounded-xl bg-red-500/10 border border-red-500/20 p-4 flex items-start gap-3 text-red-400">
                            <AlertCircle className="h-5 w-5 shrink-0" />
                            <p className="text-sm">{error}</p>
                        </div>
                    )}

                    {result && !error && (
                        <div className="rounded-xl bg-green-500/10 border border-green-500/20 p-4 flex items-center gap-3 text-green-400">
                            <CheckCircle className="h-5 w-5 shrink-0" />
                            <p className="text-sm">Prediction generated successfully ({result.length} days).</p>
                        </div>
                    )}
                </div>

                {/* Map & Chart Area */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Map */}
                    <div className="h-[300px] w-full bg-white/5 rounded-2xl border border-white/10 overflow-hidden relative">
                        {(lat && lon) ? (
                            <ForecastMap lat={parseFloat(lat)} lon={parseFloat(lon)} property={property} />
                        ) : (
                            <div className="flex h-full items-center justify-center text-slate-500">
                                Enter coordinates to view map
                            </div>
                        )}
                    </div>

                    {/* Chart */}
                    <div className="h-[350px] w-full bg-white/5 rounded-2xl border border-white/10 p-6">
                        <h3 className="text-lg text-white mb-4">10-Day Forecast ({property})</h3>
                        {result ? (
                            <ResponsiveContainer width="100%" height="80%">
                                <LineChart data={result}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                                    <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} />
                                    <YAxis stroke="#94a3b8" fontSize={12} domain={['auto', 'auto']} />
                                    <Tooltip contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', color: '#fff' }} />
                                    <Line type="monotone" dataKey="value" stroke="#a78bfa" strokeWidth={3} dot={{ r: 4 }} />
                                </LineChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="flex h-full items-center justify-center text-slate-500">
                                No prediction data yet.
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default LLMForecast;
