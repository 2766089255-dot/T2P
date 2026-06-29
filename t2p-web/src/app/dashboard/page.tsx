'use client';

import { useState, useEffect } from 'react';
import axios from 'axios';
import Link from 'next/link';
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  Radar, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend
} from 'recharts';
import { Loader2, ArrowLeft, Lightbulb } from 'lucide-react';
import { useUser } from '@/context/UserContext';
import { API_BASE } from '@/lib/config';

const truncateTopic = (name: string, maxLen = 11) =>
  name.length > maxLen ? name.slice(0, maxLen) + '…' : name;

export default function Dashboard() {
  const { userId } = useUser();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (userId) {
      fetchProgress();
    }
  }, [userId]);

  const fetchProgress = async () => {
    if (!userId) return;
    setLoading(true);
    setError('');
    try {
      const res = await axios.get(`${API_BASE}/user/progress/${userId}`);
      if (res.data.success) {
        setData(res.data.topics_status);
      } else {
        setError('Failed to retrieve data, please check username。');
      }
    } catch (e) {
      setError('Failed to retrieve data, please confirm that the backend has been started。');
    } finally {
      setLoading(false);
    }
  };

  // 用户未登录状态
  if (!userId) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#FBFBFE]">
        <div className="bg-white p-8 rounded-3xl shadow-lg text-center">
          <Lightbulb className="w-10 h-10 text-indigo-500 mx-auto mb-4" />
          <p className="text-slate-600 font-bold mb-4">Please log in as a user on the homepage first</p>
          <Link href="/" className="text-indigo-600 font-bold hover:underline">
            Return to Practice
          </Link>
        </div>
      </div>
    );
  }

  // 加载状态
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#FBFBFE]">
        <Loader2 className="animate-spin text-indigo-600 w-8 h-8" />
      </div>
    );
  }

  const radarData = data
    ? Object.entries(data).map(([topic, info]: any) => ({
        topic: truncateTopic(topic),
        mastery: Math.round(info.mastery_score * 100),
      }))
    : [];

  const barData = data
    ? Object.entries(data).map(([topic, info]: any) => ({
        topic: truncateTopic(topic),
        level: info.current_level,
        count: info.completed_count,
      }))
    : [];

  return (
    <div className="min-h-screen bg-[#FBFBFE] pb-20">
      <div className="h-1.5 bg-gradient-to-r from-indigo-600 to-violet-600" />
      <main className="max-w-4xl mx-auto py-12 px-6">
        {/* 顶部导航 */}
        <div className="flex items-center justify-between mb-10">
          <Link
            href="/"
            className="flex items-center gap-2 text-slate-800 hover:text-indigo-600 text-xs font-bold uppercase tracking-wider transition-colors"
          >
            <ArrowLeft size={16} />
            Return to Practice
          </Link>
        </div>

        {error && (
          <div className="bg-white rounded-[2.5rem] p-6 mb-10 border border-red-200 text-red-500 text-sm font-bold text-center">
            {error}
          </div>
        )}

        {data && (
          <div className="space-y-8">
            <div className="bg-white rounded-[3rem] p-8 shadow-sm border border-slate-200/50">
              <h2 className="text-sm font-bold text-slate-700 mb-6">📐 Topic Proficiency Radar Chart</h2>
              <div className="flex justify-center">
                <RadarChart width={500} height={400} data={radarData}>
                  <PolarGrid stroke="#e2e8f0" />
                  <PolarAngleAxis dataKey="topic" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
                  <Radar
                    name="Proficiency (%)"
                    dataKey="mastery"
                    stroke="#6366f1"
                    fill="#6366f1"
                    fillOpacity={0.3}
                  />
                </RadarChart>
              </div>
            </div>

            <div className="bg-white rounded-[3rem] p-8 shadow-sm border border-slate-200/50">
              <h2 className="text-sm font-bold text-slate-700 mb-6">📊 Level and practice frequency</h2>
              <div className="flex justify-center">
                <BarChart width={500} height={400} data={barData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="topic" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="level" fill="#10b981" name="Current Level" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="count" fill="#f59e0b" name="Practice count" radius={[4, 4, 0, 0]} />
                </BarChart>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}