'use client';

import { useState, useEffect, useCallback, useRef, useSyncExternalStore } from 'react';
import axios from 'axios';
import Image from 'next/image';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import SignatureCanvas from 'react-signature-canvas';
import { InlineMath, BlockMath } from "react-katex";
import 'katex/dist/katex.min.css';
import {
  Sparkles, Loader2, BrainCircuit,
  ChevronRight, Database, RefreshCw,
  SlidersHorizontal, Trash2, Send, X,
  CheckCircle2, AlertCircle, Lightbulb,
  Camera, FolderOpen, RotateCcw, User, LogIn, BarChart3
} from 'lucide-react';
import { useUser } from '@/context/UserContext';
import { API_BASE } from '@/lib/config';

interface Problem {
  id: string;
  topic: string;
  sub_topic?: string;
  problem_statement: string;
  difficulty: number;
  mode?: string;
  question_type?: string;
  scaffolding?: Array<{ step: number; hint: string }>;
  options?: Record<string, string>;
  answer?: string;
  correct_values?: string[];
}

interface AuditResult {
  is_correct: boolean;
  logic_alignment_score: number;
  error_analysis: string;
  tutor_feedback: string;
  next_hint: string;
  ocr_text?: string;
}

interface GeneratePayload {
  topics: string[];
  num: number;
  mode: string;
  difficulty: number;
  question_type: string;
  user_id?: string;
}

const STORAGE_PROBLEMS = 't2p_problems';
const STORAGE_AUDITS = 't2p_audits';

// Tool function: Check if an object can be securely JSON serialized
const isSerializable = (obj: unknown): boolean => {
  try {
    JSON.stringify(obj);
    return true;
  } catch {
    return false;
  }
};

const subscribeToClient = () => () => {};
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

const loadStoredProblems = (): Problem[] => {
  if (typeof window === 'undefined') return [];
  try {
    const saved = localStorage.getItem(STORAGE_PROBLEMS);
    if (!saved) return [];
    const parsed: unknown = JSON.parse(saved);
    return Array.isArray(parsed) ? (parsed.filter(isSerializable) as Problem[]) : [];
  } catch {
    return [];
  }
};

const loadStoredAudits = (): Record<string, AuditResult> => {
  if (typeof window === 'undefined') return {};
  try {
    const saved = localStorage.getItem(STORAGE_AUDITS);
    if (!saved) return {};
    const parsed: unknown = JSON.parse(saved);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => isSerializable(value))
    ) as Record<string, AuditResult>;
  } catch {
    return {};
  }
};

const renderMathContent = (text: string) => {
  if (!text) return null;
  
  // Extended regular expression:
  // 1. (\$\$[\s\S]*?\$\$) -> Match $$block level$$
  // 2. (\$[^$]+\$) -> Match $in line$
  // 3. (\\\[[\s\S]*?\\\]) -> Match \[block level\]
  // 4. (\\\(.*?\\\)) -> Match \(in line\)
  const parts = text.split(/(\$\$[\s\S]*?\$\$|\$[^$]+\$|\\\[[\s\S]*?\\\]|\\\(.*?\\\))/g);

  return parts.map((part, index) => {
    // Processing block level formula:$$...$$ or \[...\]
    if ((part.startsWith('$$') && part.endsWith('$$')) || 
        (part.startsWith('\\[') && part.endsWith('\\]'))) {
      const math = part.startsWith('$$') ? part.slice(2, -2) : part.slice(2, -2);
      return <BlockMath key={index} math={math} />;
    } 
    // Processing intra line formulas:$...$ or \(...\)
    else if ((part.startsWith('$') && part.endsWith('$')) || 
             (part.startsWith('\\(') && part.endsWith('\\)'))) {
      const math = part.startsWith('$') ? part.slice(1, -1) : part.slice(2, -2);
      return <InlineMath key={index} math={math} />;
    }
    // Normal Text
    return <span key={index}>{part}</span>;
  });
};
export default function T2PHome() {
  const { userId, setUserId, login } = useUser();
  const mounted = useSyncExternalStore(subscribeToClient, getClientSnapshot, getServerSnapshot);
  const [loading, setLoading] = useState(false);
  const [problems, setProblems] = useState<Problem[]>(loadStoredProblems);
  const [error, setError] = useState<string | null>(null);

  const [activeSolvingId, setActiveSolvingId] = useState<string | null>(null);
  const [isSubmittingDrawing, setIsSubmittingDrawing] = useState(false);
  const [auditResult, setAuditResult] = useState<Record<string, AuditResult>>(loadStoredAudits);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [typedAnswer, setTypedAnswer] = useState("");

  const [scaffoldingVisible, setScaffoldingVisible] = useState<Record<string, boolean>>({});

  const sigCanvas = useRef<SignatureCanvas>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const [selectedTopic, setSelectedTopic] = useState("");
  const [selectedMode, setSelectedMode] = useState("drill");
  const [difficulty, setDifficulty] = useState(3);
  const [topicOptions, setTopicOptions] = useState<string[]>([]);
  const [questionType, setQuestionType] = useState("calculation");

  const fetchTopics = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/topics`);
      if (res.data.success) {
        const topics: string[] = res.data.topics;
        setTopicOptions(topics);
        setSelectedTopic(current => current || topics[0] || '');
      }
    } catch {
      setError("Unable to connect to the backend. Please start api_server.py.");
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void fetchTopics(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [fetchTopics]);

  // Persist problems to local storage (with exception protection)
  useEffect(() => {
    if (!mounted || typeof window === 'undefined') return;
    try {
      localStorage.setItem(STORAGE_PROBLEMS, JSON.stringify(problems));
    } catch (e) {
      console.error('Failed to save title, attempt to remove non serializable data ...', e);
      // Filter out questions that cause serialization failure
      const safeProblems = problems.filter(p => isSerializable(p));
      // Even if all failures occur, do not empty the original storage
      try {
        localStorage.setItem(STORAGE_PROBLEMS, JSON.stringify(safeProblems));
      } catch (e2) {
        console.error('Secondary save failed, please manually clear cache or generate new questions', e2);
      }
    }
  }, [problems, mounted]);

  // Persist audits to local storage (with exception protection)
  useEffect(() => {
    if (!mounted || typeof window === 'undefined') return;
    try {
      localStorage.setItem(STORAGE_AUDITS, JSON.stringify(auditResult));
    } catch (e) {
      console.error('Failed to save audit results, attempting to remove abnormal data...', e);
      const safeAudits: Record<string, AuditResult> = {};
      Object.entries(auditResult).forEach(([id, val]) => {
        if (isSerializable(val)) safeAudits[id] = val;
      });
      try {
        localStorage.setItem(STORAGE_AUDITS, JSON.stringify(safeAudits));
      } catch (e2) {
        console.error('Failed to save audit results twice', e2);
      }
    }
  }, [auditResult, mounted]);

  const handleLogin = async () => {
    const success = await login();
    if (success) {
      alert(`User ${userId} Logged in`);
    } else {
      alert("Login failed");
    }
  };

  const refineStatement = (text: string) => {
    if (!text || typeof text !== 'string') return "";
    let res = text;
    res = res.replace(/\\\\+/g, '\\');
    res = res.replace(/\\\(/g, '$').replace(/\\\)/g, '$');
    res = res.replace(/\\\[/g, '\n$$\n').replace(/\\\]/g, '\n$$\n');
    res = res.replace(/\\\$/g, '$');
    res = res.replace(/\\\[/g, '$$').replace(/\\\]/g, '$$');
    res = res.replace(/\\\s+begin\{/g, '\\begin{');
    res = res.replace(/\\\s+end\{/g, '\\end{');
    res = res.replace(/\\?(quad|qquad|enspace|thickspace|vspace\{.*?\}|hspace\{.*?\})/g, ' ');
    res = res.replace(/([a-zA-Z0-9\u4e00-\u9fa5])\$/g, '$1 $');
    res = res.replace(/\$([a-zA-Z0-9\u4e00-\u9fa5])/g, '$ $1');
    res = res.replace(/\s+/g, ' ');
    return res.trim();
  };

  const prepareOptionText = (text: string) => {
    if (!text) return text;
    if (/\$/.test(text)) return refineStatement(text);
    if (/\\[a-zA-Z]+/.test(text)) return `$${refineStatement(text)}$`;
    return refineStatement(text);
  };

  const generateProblems = async () => {
    setLoading(true);
    setError(null);
    setSelectedImage(null);
    try {
      const payload: GeneratePayload = {
        topics: [selectedTopic],
        num: 1,
        mode: selectedMode,
        difficulty: difficulty,
        question_type: questionType
      };
      if (userId) payload.user_id = userId;
      const response = await axios.post(`${API_BASE}/generate`, payload);
      if (response.data.success) {
        const rawProblems: Problem[] = Array.isArray(response.data.data) ? response.data.data : [];
        // Pre check: Only accepts serializable questions
        const safeProblems = rawProblems.filter((p) => {
          if (!isSerializable(p)) {
            console.warn('Discard questions that cannot be serialized:', p);
            return false;
          }
          return true;
        });
        if (safeProblems.length < rawProblems.length) {
          setError('Some questions contain abnormal data and have been automatically filtered');
        }
        if (safeProblems.length > 0) {
          setProblems(prev => [...prev, ...safeProblems]);
          setActiveSolvingId(safeProblems[safeProblems.length - 1].id);
        } else {
          setError('Generation failed, returned data exception');
        }
      }
    } catch {
      setError("Generation failed, please check network connection or API quota");
    } finally {
      setLoading(false);
    }
  };

  const adaptiveGenerate = async () => {
    if (!userId) {
      alert("Please enter and log in your username first");
      return;
    }
    setLoading(true);
    setError(null);
    setSelectedImage(null);
    try {
      const response = await axios.post(`${API_BASE}/generate`, {
        topics: [],
        num: 1,
        user_id: userId
      });
      if (response.data.success) {
        const rawProblems: Problem[] = Array.isArray(response.data.data) ? response.data.data : [];
        const safeProblems = rawProblems.filter((p) => isSerializable(p));
        if (safeProblems.length < rawProblems.length) {
          setError('Some questions are abnormal and have been automatically filtered');
        }
        if (safeProblems.length > 0) {
          setProblems(prev => [...prev, ...safeProblems]);
          setActiveSolvingId(safeProblems[0].id);
        } else {
          setError('AI recommendation question data is abnormal, please try again later');
        }
      }
    } catch {
      setError("Generation failed, please check network connection or API quota");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setSelectedImage(reader.result as string);
        sigCanvas.current?.clear();
      };
      reader.readAsDataURL(file);
    }
  };

  const submitMCQ = async (problem: Problem, chosen: string) => {
    setIsSubmittingDrawing(true);
    try {
      const res = await axios.post(`${API_BASE}/audit`, {
        problem_id: problem.id,
        student_work_image: `The option I have chosen is: ${chosen}`,
        is_exam_mode: selectedMode === 'exam'
      });
      if (res.data.success) {
        const resultData: AuditResult = {
          is_correct: res.data.is_correct,
          logic_alignment_score: res.data.logic_alignment_score || 0,
          error_analysis: res.data.error_analysis || '',
          tutor_feedback: res.data.tutor_feedback || '',
          next_hint: res.data.next_hint || '',
          ocr_text: res.data.ocr_text || ''
        };
        setAuditResult(prev => ({ ...prev, [problem.id]: resultData }));
        if (userId) {
          axios.post(`${API_BASE}/user/record`, {
            user_id: userId,
            topic: problem.topic,
            logic_alignment_score: resultData.logic_alignment_score,
            is_correct: resultData.is_correct
          }).catch(console.error);
        }
      }
    } catch (err) {
      console.error("Submission failed", err);
      alert("Audit services are temporarily unavailable, please try again later");
    } finally {
      setIsSubmittingDrawing(false);
    }
  };

  const handleAISubmission = async (problem: Problem) => {
    let finalPayload = "";

    // Priority: typed text > uploaded image > signature pad
    if (typedAnswer.trim()) {
      finalPayload = typedAnswer.trim();
      setTypedAnswer(""); // clear after submit
    } else if (selectedImage) {
      finalPayload = selectedImage;
    } else if (sigCanvas.current && !sigCanvas.current.isEmpty()) {
      finalPayload = sigCanvas.current.getTrimmedCanvas().toDataURL('image/png');
    } else {
      alert("Please type your answer or draw on the pad / upload a photo");
      return;
    }

    setIsSubmittingDrawing(true);
    try {
      const res = await axios.post(`${API_BASE}/audit`, {
        problem_id: problem.id,
        student_work_image: finalPayload,
        is_exam_mode: selectedMode === 'exam'
      });

      if (res.data.success) {
        const resultData: AuditResult = {
          is_correct: res.data.is_correct,
          logic_alignment_score: res.data.logic_alignment_score || 0,
          error_analysis: res.data.error_analysis || '',
          tutor_feedback: res.data.tutor_feedback || '',
          next_hint: res.data.next_hint || '',
          ocr_text: res.data.ocr_text || ''
        };

        setAuditResult(prev => ({ ...prev, [problem.id]: resultData }));

        if (userId) {
          axios.post(`${API_BASE}/user/record`, {
            user_id: userId,
            topic: problem.topic,
            logic_alignment_score: resultData.logic_alignment_score,
            is_correct: resultData.is_correct
          }).catch(console.error);
        }
      }
    } catch (err) {
      console.error("Submission failed", err);
      alert("Audit services are temporarily unavailable, please try again later");
    } finally {
      setIsSubmittingDrawing(false);
    }
  };

  const clearInput = () => {
    sigCanvas.current?.clear();
    setSelectedImage(null);
    setTypedAnswer("");
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (cameraInputRef.current) cameraInputRef.current.value = "";
  };

  const toggleScaffolding = (problemId: string) => {
    setScaffoldingVisible(prev => ({
      ...prev,
      [problemId]: !prev[problemId]
    }));
  };

  const handleClearAll = () => {
    setProblems([]);
    setAuditResult({});
    setActiveSolvingId(null);
    if (typeof window !== 'undefined') {
      localStorage.removeItem(STORAGE_PROBLEMS);
      localStorage.removeItem(STORAGE_AUDITS);
    }
  };

  if (!mounted) return null;

  return (
    <div className="min-h-screen bg-[#FBFBFE] text-slate-900 font-sans pb-20">
      <style jsx global>{`
        .math-renderer .katex-display {
          margin: 1.5em 0 !important;
          padding: 1.5em;
          background: #f8fafc;
          border-radius: 1.5rem;
          border: 1px solid #f1f5f9;
          overflow-x: auto;
          text-align: center;
        }
        .math-renderer .katex {
          font-size: 1.15em;
          line-height: 1.2;
        }
        .math-renderer p {
          margin-bottom: 1.25rem;
          line-height: 1.8;
        }
        .drawing-paper {
          background-color: #ffffff;
          background-image: radial-gradient(#e2e8f0 1px, transparent 0);
          background-size: 24px 24px;
        }
      `}</style>

      <div className="h-1.5 bg-gradient-to-r from-indigo-600 to-violet-600" />

      {/* User bar in the upper right corner */}
      <div className="fixed top-4 right-4 z-50 flex items-center gap-3 bg-white rounded-2xl shadow-lg border border-slate-200/50 px-5 py-2.5">
        <User size={18} className="text-slate-700" />
        <input
          type="text"
          placeholder="Username"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
          className="bg-slate-50 border border-slate-200/50 rounded-xl px-3 py-2 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-indigo-500 outline-none w-36"
        />
        <button
          onClick={handleLogin}
          className="flex items-center gap-1.5 bg-white text-slate-900 border border-slate-200/50 px-4 py-2 rounded-xl text-sm font-bold hover:bg-slate-100 hover:text-indigo-600 transition-colors shadow-sm"
        >
          <LogIn size={16} />
          login
        </button>
        <a
          href="/dashboard"
          className="flex items-center gap-1.5 text-slate-900 hover:text-indigo-600 text-sm font-bold transition-colors ml-1 bg-slate-50 border border-slate-200/50 px-4 py-2 rounded-xl"
        >
          <BarChart3 size={16} />
          Learning Kanban
        </a>
      </div>

      <main className="max-w-4xl mx-auto py-12 px-6">
        {/* Header */}
        <header className="flex flex-col items-center mb-12">
          <div className="bg-slate-900 p-3 rounded-2xl mb-4 shadow-2xl">
            <BrainCircuit className="text-white w-7 h-7" />
          </div>
          <h1 className="text-4xl font-black tracking-tight mb-2">
            T2P <span className="text-indigo-600">Mentor</span>
          </h1>
          <div className="flex items-center gap-2 text-slate-400 text-[10px] font-black uppercase tracking-[0.2em]">
            <Database size={12} />
            <span>Structured Mathematical Analytics System</span>
          </div>
        </header>

        {/* Control Panel */}
        <div className="bg-white rounded-[2.5rem] p-8 shadow-sm border border-slate-200/50 mb-10">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
            <div className="space-y-3">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest flex items-center justify-between">
                <span>Knowledge dimension</span>
                <RefreshCw size={10} className="cursor-pointer hover:text-indigo-600 transition-colors" onClick={fetchTopics} />
              </label>
              <select
                value={selectedTopic}
                onChange={(e) => setSelectedTopic(e.target.value)}
                className="w-full bg-slate-50 border-none rounded-2xl px-4 py-3.5 font-bold text-slate-700 focus:ring-2 focus:ring-indigo-500 outline-none appearance-none cursor-pointer"
              >
                {topicOptions.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>

            <div className="space-y-3">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Practice Mode</label>
              <div className="flex bg-slate-50 p-1.5 rounded-2xl h-[52px]">
                {['drill', 'exam'].map(m => (
                  <button
                    key={m}
                    onClick={() => setSelectedMode(m)}
                    className={`flex-1 rounded-xl text-[10px] font-black transition-all ${selectedMode === m ? 'bg-white shadow-sm text-indigo-600' : 'text-slate-400'}`}
                  >
                    {m.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-3">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest flex items-center justify-between">
                <span>difficulty coefficient</span>
                <span className="text-indigo-600">LV.{difficulty}</span>
              </label>
              <input
                type="range" min="1" max="5" value={difficulty}
                onChange={(e) => setDifficulty(parseInt(e.target.value))}
                className="w-full h-1.5 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-indigo-600 mt-4"
              />

              {/* Question type selection */}
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-4 block">
                Question type selection
              </label>
              <div className="flex bg-slate-50 p-1.5 rounded-2xl h-[52px]">
                {[
                  { key: 'mcq', label: 'MCQ' },
                  { key: 'fill_in', label: 'FILL‑IN' },
                  { key: 'calculation', label: 'CALC' }
                ].map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => setQuestionType(key)}
                    className={`flex-1 rounded-xl text-[10px] font-black transition-all ${questionType === key ? 'bg-white shadow-sm text-indigo-600' : 'text-slate-400'}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <button
            onClick={generateProblems}
            disabled={loading}
            className="w-full flex items-center justify-center gap-3 bg-slate-900 text-white py-5 rounded-3xl font-bold hover:bg-indigo-600 transition-all shadow-xl shadow-indigo-100 disabled:opacity-50"
          >
            <span className="flex items-center gap-3">
              {loading ? (
                <Loader2 className="animate-spin" size={18} />
              ) : (
                <Sparkles size={18} />
              )}
              <span className="min-w-[120px] text-center">
                {loading ? "Analyzing mathematical logic .." : "Generate current configuration question"}
              </span>
            </span>
          </button>

          <button
            onClick={adaptiveGenerate}
            disabled={loading}
            className="w-full mt-3 flex items-center justify-center gap-3 bg-white text-slate-900 border border-slate-200/50 py-5 rounded-3xl font-bold hover:bg-indigo-600 hover:text-white hover:border-indigo-600 transition-all shadow-sm disabled:opacity-50"
          >
            <Sparkles size={14} />
            Continue learning (AI recommendation)
          </button>

          {error && <p className="mt-4 text-center text-red-500 text-xs font-bold">{error}</p>}
        </div>

        {/* Clear all question buttons */}
        {problems.length > 0 && (
          <div className="flex justify-end mb-4">
            <button
              onClick={handleClearAll}
              className="text-xs text-slate-400 hover:text-red-500 font-bold flex items-center gap-1 transition-colors"
            >
              <Trash2 size={14} /> Clear all questions
            </button>
          </div>
        )}

        {/* Question Display and Answering Area */}
        <div className="space-y-8">
          {problems.map((problem, index) => {
            const result = auditResult[problem.id];
            const isSolving = activeSolvingId === problem.id;
            const showScaffolding = scaffoldingVisible[problem.id] || false;

            return (
              <article key={problem.id || index} className="bg-white rounded-[3rem] border border-slate-200/50 shadow-sm p-10 transition-all duration-500 overflow-hidden">
                <div className="flex items-center gap-3 mb-8">
                  <span className="bg-indigo-50 text-indigo-600 px-4 py-1 rounded-full text-[10px] font-black uppercase">
                    {problem.topic}
                  </span>
                  <ChevronRight size={12} className="text-slate-300" />
                  <span className="text-slate-400 text-[10px] font-black uppercase tracking-widest">{problem.sub_topic || "Core Concept"}</span>
                </div>

                <div className="math-renderer prose prose-slate max-w-none prose-p:text-xl text-slate-800 mb-6">
                  <ReactMarkdown
                    remarkPlugins={[remarkMath]}
                    rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                  >
                    {refineStatement(problem.problem_statement)}
                  </ReactMarkdown>
                </div>

                {/* Bracket display */}
                {problem.scaffolding && problem.scaffolding.length > 0 && (
                  <div className="mb-6">
                    <button
                      onClick={() => toggleScaffolding(problem.id)}
                      className="flex items-center gap-2 text-xs font-bold text-indigo-600 hover:text-indigo-800 transition-colors mb-2"
                    >
                      <Lightbulb size={14} />
                      {showScaffolding ? 'Hide Tips' : 'View prompts'}
                    </button>
                    {showScaffolding && (
                      <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200/50 animate-in slide-in-from-top-2 duration-300">
                        <ol className="list-decimal list-inside text-sm text-slate-700 space-y-2">
                          {problem.scaffolding.map((item) => (
                            <li key={item.step} className="pl-1">
                              <span className="font-semibold text-indigo-600">steps {item.step}:</span>{' '}
                              <ReactMarkdown
                                remarkPlugins={[remarkMath]}
                                rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                                components={{ p: ({ children }) => <span>{children}</span> }}
                              >
                                {refineStatement(item.hint)}
                              </ReactMarkdown>
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}
                  </div>
                )}

                {/* MCQ Answering area */}
                {isSolving && problem.question_type === 'mcq' && problem.options && (
                  <div className="mt-6">
                    <h3 className="text-sm font-bold text-slate-700 mb-4">Please choose an option:</h3>
                    <div className="grid grid-cols-2 gap-4">
                      {Object.entries(problem.options).map(([key, value]) => {
                        const displayValue = prepareOptionText(value);
                        return (
                          <button
                            key={key}
                            onClick={() => submitMCQ(problem, key)}
                            disabled={isSubmittingDrawing}
                            className="bg-slate-50 hover:bg-indigo-50 border border-slate-200 rounded-2xl p-4 text-left font-bold text-sm text-slate-700 transition-all"
                          >
                            <span className="text-indigo-600 mr-2">{key}.</span>{' '}
                            <ReactMarkdown
                              remarkPlugins={[remarkMath]}
                              rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                              components={{ p: ({ children }) => <span>{children}</span> }}
                            >
                              {displayValue}
                            </ReactMarkdown>
                          </button>
                        );
                      })}
                    </div>
                    {isSubmittingDrawing && <p className="text-xs text-slate-400 mt-4">Under audit ..</p>}
                  </div>
                )}

                {/* Other question types: handwriting board+photo upload */}
                {isSolving && (!problem.question_type || problem.question_type !== 'mcq') && (
                  <div className="mt-6 animate-in slide-in-from-top-4 duration-500">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-[10px] font-black text-indigo-600 uppercase tracking-[0.2em] flex items-center gap-2">
                        <Sparkles size={14} /> Intelligent Draft Book (AI Scaffolding)
                      </h3>
                      <button
                        onClick={clearInput}
                        className="p-2 text-slate-400 hover:text-red-500 transition-colors"
                        title="reset input "
                      >
                        <RotateCcw size={18} />
                      </button>
                    </div>

                    {/* Text input for typed answers (works without OCR) */}
                    <textarea
                      value={typedAnswer}
                      onChange={(e) => setTypedAnswer(e.target.value)}
                      placeholder="Type your answer here (e.g., y = -3x + 3) or draw below..."
                      className="w-full h-20 bg-slate-50 border border-slate-200 rounded-2xl p-4 text-sm font-mono text-slate-800 resize-none focus:ring-2 focus:ring-indigo-500 outline-none mb-3 placeholder:text-slate-400"
                    />

                    <div className="drawing-paper border-2 border-slate-100 rounded-[2.5rem] overflow-hidden shadow-inner relative min-h-[360px]">
                      {selectedImage ? (
                        <div className="absolute inset-0 bg-slate-50/50 flex items-center justify-center p-8">
                          <div className="relative max-h-full">
                            <Image
                              src={selectedImage}
                              alt="Uploaded work"
                              width={800}
                              height={600}
                              unoptimized
                              className="max-h-[300px] w-auto object-contain rounded-2xl shadow-2xl border-4 border-white"
                            />
                            <button
                              onClick={() => setSelectedImage(null)}
                              className="absolute -top-3 -right-3 bg-red-500 text-white p-1.5 rounded-full shadow-lg hover:bg-red-600 transition-colors"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        </div>
                      ) : (
                        <SignatureCanvas
                          ref={sigCanvas}
                          penColor="#1e293b"
                          canvasProps={{
                            className: "w-full h-[360px] cursor-crosshair",
                            style: { width: '100%', height: '360px' }
                          }}
                        />
                      )}

                      {isSubmittingDrawing && (
                        <div className="absolute inset-0 bg-white/80 backdrop-blur-sm flex flex-col items-center justify-center z-20">
                          <Loader2 className="animate-spin text-indigo-600 mb-2" size={32} />
                          <p className="text-[10px] font-black text-indigo-600 uppercase tracking-widest">AI is auditing the deduction logic ...</p>
                        </div>
                      )}
                    </div>

                    <div className="w-full flex justify-between items-center mt-4 gap-3">
                      <button
                        onClick={() => handleAISubmission(problem)}
                        disabled={isSubmittingDrawing}
                        className="flex items-center justify-center gap-2 bg-slate-900 text-white px-6 py-3 rounded-xl font-bold text-xs hover:bg-indigo-600 transition-colors shadow-md disabled:opacity-50"
                      >
                        <Send size={14} /> {selectedImage ? "Upload photos and audit" : "Submit handwritten answer"}
                      </button>

                      <div className="flex gap-3">
                        <input
                          type="file"
                          accept="image/*"
                          capture="environment"
                          ref={cameraInputRef}
                          onChange={handleFileChange}
                          className="hidden"
                          style={{ position: 'absolute', opacity: 0, pointerEvents: 'none', width: 0, height: 0 }}
                        />
                        <button
                          onClick={() => cameraInputRef.current?.click()}
                          className="w-12 h-12 bg-white border border-slate-200/50 rounded-2xl flex items-center justify-center hover:bg-slate-50 active:scale-95 transition-all shadow-sm"
                          title="Take a photo and upload"
                        >
                          <Camera size={20} className="text-indigo-600" />
                        </button>

                        <input
                          type="file"
                          accept="image/*"
                          ref={fileInputRef}
                          onChange={handleFileChange}
                          className="hidden"
                          style={{ position: 'absolute', opacity: 0, pointerEvents: 'none', width: 0, height: 0 }}
                        />
                        <button
                          onClick={() => fileInputRef.current?.click()}
                          className="w-12 h-12 bg-white border border-slate-200/50 rounded-2xl flex items-center justify-center hover:bg-slate-50 active:scale-95 transition-all shadow-sm"
                          title="Select from folder"
                        >
                          <FolderOpen size={20} className="text-indigo-500" />
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {result && (
                  <div className={`mt-10 p-8 rounded-[2rem] border-2 animate-in slide-in-from-bottom-4 duration-500 ${result.is_correct ? 'bg-emerald-50/50 border-emerald-100' : 'bg-amber-50/50 border-amber-100'}`}>
                    <div className="flex items-start gap-4">
                      {result.is_correct ? (
                        <CheckCircle2 className="text-emerald-500 mt-1 shrink-0" size={24} />
                      ) : (
                        <AlertCircle className="text-amber-500 mt-1 shrink-0" size={24} />
                      )}
                      <div className="w-full space-y-6">
                        <h4 className={`font-black text-xs uppercase tracking-widest ${result.is_correct ? 'text-emerald-700' : 'text-amber-700'}`}>
                          AI Mentor Audit Report
                        </h4>

                        <div>
                          <div className="flex justify-between text-xs font-bold mb-1">
                            <span className="text-slate-500">Logical alignment rating</span>
                            <span className={result.logic_alignment_score >= 70 ? 'text-emerald-600' : 'text-amber-600'}>
                              {result.logic_alignment_score}/100
                            </span>
                          </div>
                          <div className="w-full bg-slate-200 rounded-full h-2">
                            <div
                              className={`h-2 rounded-full transition-all ${result.logic_alignment_score >= 80 ? 'bg-emerald-500' : result.logic_alignment_score >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}
                              style={{ width: `${result.logic_alignment_score}%` }}
                            ></div>
                          </div>
                        </div>

                        {result.error_analysis && (
                          <div className="bg-white/70 rounded-xl p-4 border border-slate-200">
                            <p className="text-xs font-bold text-slate-500 uppercase mb-2">Error analysis</p>
                            <div className="text-sm text-slate-700">{renderMathContent(result.error_analysis)}</div>
                          </div>
                        )}

                        {result.tutor_feedback && (
                          <div className="bg-white/70 rounded-xl p-4 border border-slate-200">
                            <p className="text-xs font-bold text-slate-500 uppercase mb-2">Supervisor&apos;s advice</p>
                            <div className="text-sm text-slate-700">{renderMathContent(result.tutor_feedback)}</div>
                          </div>
                        )}

                        {result.next_hint && (
                          <div className="bg-white/70 rounded-xl p-4 border border-indigo-200 flex items-start gap-2">
                            <Lightbulb size={16} className="text-indigo-500 mt-0.5 shrink-0" />
                            <div>
                              <p className="text-xs font-bold text-indigo-600 uppercase mb-1">Next step guidance</p>
                              <div className="text-sm text-slate-700">{renderMathContent(result.next_hint)}</div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                <div className="mt-8 flex items-center justify-between pt-6 border-t border-slate-100">
                  <div className="flex gap-1">
                    {[...Array(5)].map((_, i) => (
                      <div
                        key={i}
                        className={`w-6 h-1.5 rounded-full ${i < Number(problem.difficulty) ? 'bg-indigo-500' : 'bg-slate-100'}`}
                      />
                    ))}
                  </div>
                  {!isSolving && (
                    <button
                      onClick={() => setActiveSolvingId(problem.id)}
                      className="bg-slate-900 hover:bg-indigo-600 text-white px-8 py-3 rounded-2xl font-black text-xs transition-all shadow-lg flex items-center justify-center gap-2"
                    >
                      Start answering and auditing <ChevronRight size={14} />
                    </button>
                  )}
                  {isSolving && (
                    <button
                      onClick={() => {
                        setActiveSolvingId(null);
                        setSelectedImage(null);
                      }}
                      className="text-slate-400 hover:text-slate-600 font-black text-xs uppercase tracking-widest flex items-center gap-2"
                    >
                      Put away the answer area <X size={14} />
                    </button>
                  )}
                </div>
              </article>
            );
          })}

          {!loading && problems.length === 0 && (
            <div className="text-center py-20 border-2 border-dashed border-slate-200 rounded-[3rem]">
              <SlidersHorizontal className="w-10 h-10 text-slate-200 mx-auto mb-4" />
              <p className="text-slate-400 font-bold text-xs uppercase tracking-widest">Please select the dimension above to start generating</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
